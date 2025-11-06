from __future__ import annotations

import os, time, math
from typing import Optional, Tuple, Dict, Any, List
from decimal import Decimal
import redis
import uuid
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ..models import UserAccount
from .margin_utils import aggregate_user_margin_and_pnl
from marketdata.contracts import spec_for  # or specfor
from marketdata.models import Fill
from decimal import Decimal
from typing import Optional, Dict, Any
import time

from django.db import transaction
from django.db.models import F

# adjust this import path if redis_ops.py lives outside the models' app
from marketdata.models import UserAccount, LedgerEntry



def generate_position_id() -> str:
    return str(uuid.uuid4())

# Redis client
def get_redis() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    return redis.from_url(url, decode_responses=True)

# Key helpers
def k_pos(uid: int | str, position_id: str) -> str:
    return f"pos:{uid}:{position_id}"

def k_posidx(uid: int | str) -> str:
    return f"posidx:{uid}"

def k_symidx(symbol: str) -> str:
    return f"symidx:{symbol}"

# ---- Math helpers (netting) ----
def _apply_fill_math(net_lots: float, avg_entry: Optional[float],
    fill_lots: float, fill_price: float, contract_size: int
) -> Tuple[float, Optional[float], float]:
    L = float(net_lots)
    q = float(fill_lots)
    p = float(fill_price)
    realized = Decimal('0.0')
    
    if abs(L) < Decimal('1e-12'):
        return (q, p, Decimal('0.0') if q != 0 else Decimal('0.0'))
    
    if (L > 0 and q > 0) or (L < 0 and q < 0):
        Lp = L + q
        avg = ((avg_entry or p) * L + p * q) / Lp
        return (Lp, avg, Decimal('0.0'))
    
    reduce_qty = min(abs(q), abs(L)) if q != 0 else abs(L)
    
    if L > 0:
        realized = (p - avg_entry) * contract_size * reduce_qty
    else:
        realized = (avg_entry - p) * contract_size * reduce_qty
    
    Lp = L + q
    
    if abs(Lp) < Decimal('1e-12'):
        return (Decimal('0.0'), None, realized)
    
    avg_entry = avg_entry or p
    
    return (Lp, avg_entry, realized)

# Atomic Redis ops
def apply_fill_netting(
    uid: int | str,
    position_id: str | None,
    fill_lots: float,
    fill_price: float,
    contract_size: int,
    leverage: int,
    mode: str = "netting",
    side: Optional[str] = None,
    symbol: Optional[str] = None,
    open_time: Optional[int] = None
) -> Dict[str, Any]:

    r = get_redis()
    now = int(time.time())

    if position_id is None:
        position_id = generate_position_id()

    key = k_pos(uid, position_id)

    with r.pipeline() as p:
        p.hgetall(key)
        pos = p.execute()[0] or {}

    L = float(pos.get("net_lots", 0) or 0)
    avg = float(pos["avg_entry"]) if pos.get("avg_entry") not in (None, "", "None") else None

    new_net, new_avg, realized = _apply_fill_math(L, avg, fill_lots, fill_price, contract_size)

    # we need the symbol even if we fully close (before we blank it below)
    # resolved_symbol = symbol if symbol else (pos.get("symbol") or "")
    resolved_symbol = (symbol or pos.get("symbol", "")).upper()

    with r.pipeline() as p:
        if abs(Decimal(str(new_net))) < Decimal('1e-12'):
            # Closing position – remove from index, blank fields
            p.hset(key, mapping={
                "net_lots": 0.0, "avg_entry": "",
                "updated_at": now, "mode": mode,
                "side": "", "symbol": "", "open_time": ""
            })
            p.srem(k_posidx(uid), position_id)
        else:
            resolved_side = (
                side if side else ("Sell" if new_net < 0 else "Buy" if new_net > 0 else "")
            )
            if not resolved_symbol:
                raise Exception("Missing symbol value for position!")

            p.hset(key, mapping={
                "net_lots": new_net,
                "avg_entry": new_avg if new_avg is not None else "",
                "updated_at": now,
                "mode": mode,
                "side": resolved_side,
                "symbol": resolved_symbol,
                "open_time": open_time or pos.get("open_time") or now,
                "leverage": leverage,   # keep leverage stored on the position hash
            })

            # Only add to index if we're opening a new position or changing lots
            if abs(Decimal(str(L))) < Decimal('1e-12') or abs(Decimal(str(new_net - L))) > Decimal('1e-12'):
                p.sadd(k_posidx(uid), position_id)

                # Ensure user is registered for tick updates of this symbol
                p.sadd(k_symidx(resolved_symbol), uid)

        p.execute()

    # ---- NEW: Book realized P&L to DB balance + ledger (atomic) ----
    realized_dec = Decimal(str(realized or 0))
    if realized_dec != 0:
        with transaction.atomic():
            # lock the row so concurrent closes/opens don't race the balance
            acc = UserAccount.objects.select_for_update().get(user_id=int(uid))
            acc.balance = F('balance') + realized_dec
            acc.save(update_fields=['balance'])

            # optional but strongly recommended for audit
            LedgerEntry.objects.create(
                user_id=int(uid),
                symbol=resolved_symbol or "",
                kind="realized_pnl",
                amount=realized_dec,
                ref=str(position_id),
            )
    # ---- end NEW ----

    return {
        "position_id": position_id,
        "new_net": new_net,
        "new_avg": new_avg,
        "realized": realized,
        "updated_at": now,
    }


def mark_to_market(uid: int | str, position_id: str, mark: float,
    contract_size: int, leverage: int) -> Dict[str, Any]:
    r = get_redis()
    key = k_pos(uid, position_id)
    now = int(time.time())

    with r.pipeline() as p:
        p.hgetall(key)
        pos = p.execute()[0] or {}

    net = float(pos.get("net_lots", 0) or 0)
    if abs(net) < Decimal('1e-12'):
        with r.pipeline() as p:
            p.hset(key, mapping={"last_mark": mark, "unreal_pnl": 0.0, "margin": 0.0, "updated_at": now})
            p.execute()
        return {"unreal_pnl": 0.0, "margin": 0.0, "last_mark": mark, "updated_at": now, "user_updated": False}

    avg_entry = float(pos.get("avg_entry") or mark)
    pnl = (mark - avg_entry) * contract_size * net
    notional = abs(contract_size * net * mark)

    # Use per-position leverage from Redis, fallback to supplied leverage
    lev = int(pos.get("leverage", leverage))
    margin = notional / max(1, lev)

    # Update position first
    with r.pipeline() as p:
        p.hset(key, mapping={
            "last_mark": mark,
            "unreal_pnl": pnl,
            "margin": margin,
            "updated_at": now
        })
        p.execute()

    # Now update the aggregated UserAccount totals
    try:
        user_id = int(uid)
        account = UserAccount.objects.get(user_id=user_id)

        # Aggregate from all positions to get total unrealized PnL and used margin
        position_ids = r.smembers(k_posidx(user_id)) or set()
        total_unrealized_pnl = Decimal('0.0')
        total_used_margin = Decimal('0.0')

        for pos_id in position_ids:
            pos = r.hgetall(k_pos(user_id, pos_id))
            if pos and pos.get("unreal_pnl") is not None:
                total_unrealized_pnl += Decimal(str(pos.get("unreal_pnl")))
                total_used_margin += Decimal(str(pos.get("margin", "0")))

        # Update UserAccount with aggregated totals
        from django.db import transaction
        with transaction.atomic():
            account.unrealized_pnl = total_unrealized_pnl
            account.used_margin = total_used_margin
            account.save(update_fields=['unrealized_pnl', 'used_margin'])

        return {
            "unreal_pnl": pnl, 
            "margin": margin, 
            "last_mark": mark, 
            "updated_at": now,
            "user_updated": True,
            "total_unrealized_pnl": float(total_unrealized_pnl),
            "total_used_margin": float(total_used_margin)
        }
        
    except Exception as e:
        print(f"mark_to_market: Error updating UserAccount for {uid}: {e}")
        return {
            "unreal_pnl": pnl, 
            "margin": margin, 
            "last_mark": mark, 
            "updated_at": now,
            "user_updated": False
        }

def positions_snapshot(uid: int | str) -> List[Dict[str, Any]]:
    r = get_redis()
    position_ids = r.smembers(k_posidx(uid)) or set()
    positions = []
    
    with r.pipeline() as p:
        for pos_id in position_ids:
            p.hgetall(k_pos(uid, pos_id))
        results = p.execute()

    for pos_id, fields in zip(position_ids, results):
        if not fields:
            continue
        
        net_lots = float(fields.get("net_lots", 0))
        pos = {
            "id": pos_id,
            "symbol": fields.get("symbol", ""),
            "net_lots": net_lots,
            "open_price": float(fields.get("avg_entry", 0)),
            "unreal_pnl": float(fields.get("unreal_pnl", 0)),
            "margin": float(fields.get("margin", 0)),
            "mark": float(fields.get("last_mark", 0)),
            "open_time": int(fields.get("open_time") or fields.get("updated_at", 0)),
            # Automatically derive side for display
            "side": "Sell" if net_lots < 0 else "Buy" if net_lots > 0 else "",
            "ts": int(fields.get("updated_at", 0)),
        }
        
        positions.append(pos)
    
    return positions

def exit_position(user_id, position_id, exit_price, mode="netting"):
    r = get_redis()
    key = k_pos(user_id, position_id)
    pos = r.hgetall(key)
    
    if not pos:
        raise Exception("Position not found")

    net_lots = float(pos.get("net_lots", 0))
    if abs(net_lots) < 1e-12:
        return {"message": "Position already closed"}

    symbol = pos.get("symbol")
    side = "Sell" if net_lots > 0 else "Buy"
    opposite_lots = -net_lots  # to zero out net lots

    # Apply fill netting and get realized info
    res = apply_fill_netting(
        user_id, position_id,
        fill_lots=opposite_lots,
        fill_price=exit_price,
        contract_size=spec_for(symbol).contract_size,
        leverage=int(pos.get("leverage")),
        mode=mode,
        side=side,
        symbol=symbol,
        open_time=int(pos.get("open_time") or time.time())
    )

    # Persist the fill with realized PnL
    try:
        Fill.objects.create(
            userid=user_id,
            symbol=symbol,
            side=side,
            lots=abs(opposite_lots),
            price=exit_price,
            realizedpnl=res.get("realized", 0),
            positionid=position_id,
            ts=int(time.time())
        )
    except Exception as e:
        print(f"Error persisting Fill on exit_position: {e}")

    # Update aggregated UserAccount totals after closing
    try:
        user_id = int(user_id)
        account = UserAccount.objects.get(user_id=user_id)

        position_ids = r.smembers(k_posidx(user_id)) or set()
        total_unrealized_pnl = Decimal('0.0')
        total_used_margin = Decimal('0.0')

        for pos_id in position_ids:
            pos = r.hgetall(k_pos(user_id, pos_id))
            if pos and pos.get("unreal_pnl") is not None:
                total_unrealized_pnl += Decimal(str(pos.get("unreal_pnl")))
                total_used_margin += Decimal(str(pos.get("margin", "0")))

        from django.db import transaction
        with transaction.atomic():
            account.unrealized_pnl = total_unrealized_pnl
            account.used_margin = total_used_margin
            account.save(update_fields=['unrealized_pnl', 'used_margin'])

    except Exception as e:
        print(f"exit_position: Error updating UserAccount for {user_id}: {e}")

    return res
