# marketdata/services/admin_broadcast_trades.py
from decimal import Decimal, ROUND_HALF_EVEN
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import F

from marketdata.contracts import spec_for
from marketdata.models_admintrades import AdminBroadcastTrade, AdminTradeApplication
from marketdata.models import LedgerEntry, UserAccount  # adjust if your names differ

User = get_user_model()

# ---------- helpers ----------------------------------------------------------

FX_DEFAULT_CONTRACT = Decimal("100000")  # 1 lot = 100k base units (e.g., EURUSD)
GOLD_DEFAULT_CONTRACT = Decimal("100")   # common XAUUSD contract size
INDEX_DEFAULT_CONTRACT = Decimal("1")    # fallback for indices/CFDs if unknown


def _apply_capital_delta(user_id: int, delta: Decimal):
    """
    Atomically apply realized PnL to the user's account.
    Free margin increases by the same delta if used margin is unchanged.
    """
    # lock row to avoid race conditions with other updates
    acc = UserAccount.objects.select_for_update().get(user_id=user_id)
    UserAccount.objects.filter(pk=acc.pk).update(
        balance=F("balance") + delta,
        # equity=F("equity") + delta,
        # free_margin=F("free_margin") + delta,
    )


def _contract_multiplier(symbol: str) -> Decimal:
    """Get per-lot contract multiplier from spec(), else sensible defaults."""
    try:
        spec = spec_for(symbol)
        for attr in ("contract_size", "lot_size", "multiplier", "value_per_lot", "lot_value"):
            v = getattr(spec, attr, None)
            if v:
                v = Decimal(str(v))
                if v > 0:
                    return v
    except Exception:
        pass

    sym = (symbol or "").upper()
    if len(sym) == 6 and sym.isalpha():  # e.g., EURUSD
        return FX_DEFAULT_CONTRACT
    if sym.startswith("XAU"):            # e.g., XAUUSD
        return GOLD_DEFAULT_CONTRACT
    return INDEX_DEFAULT_CONTRACT

def _pnl_amount(side: str, entry: Decimal, exit_: Decimal, lots: Decimal, contract: Decimal) -> Decimal:
    move = (exit_ - entry) if side == "Buy" else (entry - exit_)
    return move * lots * contract

def _quantize_ledger(x: Decimal) -> Decimal:
    # LedgerEntry.amount appears to use 8 dp in admin
    return x.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)

def _required_margin(lots: Decimal, entry_price: Decimal, contract: Decimal, leverage: int) -> Decimal:
    # simple: margin = notional / leverage; notional = lots * contract * entry_price
    notional = lots * contract * entry_price
    return (notional / Decimal(leverage)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

def _get_free_margin(user_id: int) -> Decimal:
    # Lock row for consistency
    acc = UserAccount.objects.select_for_update().get(user_id=user_id)
    return Decimal(acc.free_margin)

# ---------- main -------------------------------------------------------------

@transaction.atomic
def apply_closed_admin_trade_on_save(trade_id: int):
    """
    When an AdminBroadcastTrade is saved with both entry and exit filled,
    apply immediately to all users in its groups if they have enough free margin.
    No realtime; just ledger + audit. Skips users without capital.
    """
    trade = AdminBroadcastTrade.objects.select_for_update().get(id=trade_id)

    # Must be fully specified
    if not (trade.entry_price and trade.exit_price and trade.lots and trade.side and trade.symbol):
        return {"applied": 0, "skipped": 0}

    # ensure final status
    if trade.status not in ("closed", "live", "draft"):
        trade.status = "closed"

    entry = Decimal(trade.entry_price)
    exit_ = Decimal(trade.exit_price)
    lots = Decimal(trade.lots)
    lev = int(trade.leverage or 500)
    contract = _contract_multiplier(trade.symbol)
    now = timezone.now()

    pnl_raw = _pnl_amount(trade.side, entry, exit_, lots, contract)
    realized_per_user = _quantize_ledger(pnl_raw)
    req_margin = _required_margin(lots, entry, contract, lev)

    user_ids = {u.id for g in trade.groups.all() for u in g.users.all()}
    applied = skipped = 0

    for uid in user_ids:
        # idempotency
        if uid in trade.applied_to_user_ids:
            continue

        # capital check
        free_margin = _get_free_margin(uid)
        if free_margin < req_margin:
            skipped += 1
            continue

        # ✅ write same kind as existing realized rows so frontend history shows it
        LedgerEntry.objects.create(
            user_id=uid,
            amount=realized_per_user,   # positive = profit, negative = loss
            kind="realized_pnl",
            ref=str(trade.ref),         # cast in case ref is UUIDField
            symbol=trade.symbol,
            ts=now,
        )

        _apply_capital_delta(uid, realized_per_user)

        # audit row
        AdminTradeApplication.objects.create(
            trade=trade, user_id=uid, realized=realized_per_user
        )

        trade.applied_to_user_ids.append(uid)
        applied += 1

    if not trade.closed_at:
        trade.closed_at = now
    trade.status = "closed"
    trade.save(update_fields=["applied_to_user_ids", "status", "closed_at"])

    return {"applied": applied, "skipped": skipped}
