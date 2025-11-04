from decimal import Decimal
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from marketdata.models import Order, Fill, PositionSnapshot, UserAccount
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from marketdata.engine.redis_ops import apply_fill_netting
from marketdata.contracts import spec_for
from marketdata.engine.margin_utils import validate_order


def on_fill(
    user_id: int,
    symbol: str,
    side: str,
    lots: float,
    price: float,
    mode: str = "netting",
    client_id: str | None = None,
    leverage: int = 500,
):
    spec = spec_for(symbol)
    norm_side = side.capitalize()  # "Buy"/"Sell"
    signed_lots = float(lots) if norm_side == "Buy" else -float(lots)

    # Validate margin/capital
    try:
        account = UserAccount.objects.get(user_id=user_id)
    except UserAccount.DoesNotExist:
        return Response({"error": "UserAccount not found"}, status=status.HTTP_400_BAD_REQUEST)

    d_lots = Decimal(str(abs(lots)))
    d_price = Decimal(str(price))
    validation = validate_order(account, d_lots, d_price, spec.contract_size, leverage)
    if not validation["ok"]:
        return Response(
            {"error": "Insufficient margin", "details": validation["error"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Apply to Redis (and book realized PnL in DB)
    res = apply_fill_netting(
        user_id,
        None,
        signed_lots,
        float(price),
        spec.contract_size,
        leverage,
        mode=mode,
        side=norm_side,
        symbol=symbol,
        open_time=None,
    )

    position_id = res["position_id"]
    realized = Decimal(str(res.get("realized", 0) or 0))

    # Push WebSocket update
    ch = get_channel_layer()
    async_to_sync(ch.group_send)(
        f"user_{user_id}",
        {
            "type": "positions_update",
            "data": {
                "symbol": symbol,
                "mark": float(price),
                "unreal_pnl": 0.0,
                "margin": 0.0,
                "ts": res["updated_at"],
            },
        },
    )

    # Persist Order / Fill / Snapshot atomically
    with transaction.atomic():
        order = None
        if client_id:
            order = (
                Order.objects.select_for_update()
                .filter(client_id=client_id, user_id=user_id)
                .first()
            )

        if order is None:
            order = Order.objects.create(
                user_id=user_id,
                symbol=symbol,
                side=norm_side,
                lots=Decimal(str(abs(lots))),
                price=Decimal(str(price)),
                type="market",
                status="filled",
                client_id=client_id,
                position_id=position_id,  # NEW
            )
        else:
            if not getattr(order, "position_id", None):
                order.position_id = position_id
                order.save(update_fields=["position_id"])

        Fill.objects.create(
            order=order,
            user_id=user_id,
            symbol=symbol,
            side=norm_side,
            lots=Decimal(str(abs(lots))),
            price=Decimal(str(price)),
            realized_pnl=realized,
        )

        # Realized PnL already ledgered inside apply_fill_netting
        PositionSnapshot.objects.create(
            user_id=user_id,
            symbol=symbol,
            net_lots=Decimal(str(res.get("new_net", 0))),
            avg_entry=Decimal(str(res.get("new_avg", 0) or 0)),
            unreal_pnl=Decimal("0"),
            margin=Decimal("0"),
            mark=Decimal(str(price)),
        )

    return res

# Working