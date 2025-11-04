# backend/marketdata/views.py
from operator import le
import os, json
import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from .serializers import OrderSerializer, FillSerializer
from .models import Order, Fill
from decimal import Decimal
from marketdata.engine.margin_utils import validate_order
from marketdata.contracts import spec_for
from marketdata.models import UserAccount
from django.db import transaction
from marketdata.engine.redis_ops import exit_position
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework import generics, permissions
from .models import Fill
from .serializers import FillSerializer
from django.db.models import Max
from django.db.models import Q
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from .serializers import ClosedTradeSerializer
from django.db.models import Sum, Max, F
from .models import Order, Fill, LedgerEntry
from .serializers import OrderSerializer, FillSerializer
from .contracts import SPECS
from .engine.redis_ops import positions_snapshot, get_redis
from .engine.positions import on_fill


def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def candles(request):
    symbol = request.GET.get("symbol", "EURUSD")
    interval = request.GET.get("interval", "1m")
    limit = int(request.GET.get("limit", "200"))

    # Map interval to Alltick kline_type
    interval_map = {
        "1m": 1, "5m": 2, "15m": 3, "30m": 4,
        "1h": 5, "4h": 6, "1d": 7
    }
    kline_type = interval_map.get(interval, 1)

    query = {
        "trace": "candles_req",
        "data": {
            "code": symbol,
            "kline_type": kline_type,
            "kline_timestamp_end": 0,
            "query_kline_num": limit,
            "adjust_type": 0
        }
    }

    url = f"{settings.ALLTICK_BASE_REST}/kline?token={settings.ALLTICK_API_KEY}&query=" \
          + requests.utils.quote(json.dumps(query))

    r = requests.get(url, timeout=10)
    j = r.json()

    # Get candle list
    kline_list = j.get("data", {}).get("kline_list", [])

    candles = [
        {
            "time": int(item["timestamp"]),  # already seconds
            "open": float(item["open_price"]),
            "high": float(item["high_price"]),
            "low": float(item["low_price"]),
            "close": float(item["close_price"]),
            "volume": float(item.get("volume", 0)),
        }
        for item in kline_list
    ]

    return JsonResponse(candles, safe=False)


@require_GET
def symbols(request):
    """
    Return lean symbol metadata for UI: precision, pip, contract_size, and display.
    """
    data = {
        k: {
            "display": v.display,
            "precision": v.precision,
            "pip": v.pip,
            "contract_size": v.contract_size,
            "min_lot": v.min_lot,
            "lot_step": v.lot_step,
            "max_lot": v.max_lot,
            "leverage_max": v.leverage_max,
        }
        for k, v in SPECS.items()
    }
    return JsonResponse(data)


class PositionsSnapshotView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snap = positions_snapshot(request.user.id)
        return Response(snap)


class SimFillView(APIView):
    """
    Temporary endpoint to simulate an executed fill and update Redis hot state.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payload = request.data or {}
        symbol = payload.get("symbol")
        side = payload.get("side")
        lots = float(payload.get("lots", 0))
        price = float(payload.get("price", 0))
        leverage = int(payload.get("leverage", 500))
        print("Levergae ", leverage)
        if not symbol or side not in ("Buy", "Sell") or lots <= 0 or price <= 0:
            return Response({"error": "invalid payload"}, status=400)

        # Your logic inside atomic transaction so that select_for_update can work correctly
        res = on_fill(request.user.id, symbol, side, lots, price, leverage=leverage)
        
        return Response({
            "ok": True,
            "symbol": symbol,
            "side": side,
            "lots": lots,
            "price": price,
            "position": {
                "net_lots": res.get("new_net", 0),
                "avg_entry": res.get("new_avg", 0),
                "realized_pnl": res.get("realized", 0),
                "updated_at": res.get("updated_at", 0),
            }
        })


class ClosePositionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        symbol = request.data.get("symbol")
        lots_req = request.data.get("lots")  # optional for partial close
        if not symbol:
            return Response({"error": "symbol required"}, status=400)

        snap = positions_snapshot(request.user.id)
        matching_positions = [p for p in snap if p.get("symbol") == symbol and abs(float(p.get("net_lots", 0))) > 0]
        if not matching_positions:
            return Response({"error": "no open position"}, status=400)

        # If you want to always close the largest, just pick the first
        pos = matching_positions[0]
        if not pos:
            return Response({"error": "no open position"}, status=400)

        net = float(pos.get("net_lots", 0))
        if abs(net) < 1e-12:
            return Response({"error": "already flat"}, status=400)

        # determine close size and side
        close_lots = float(lots_req) if lots_req else abs(net)
        if close_lots <= 0 or close_lots > abs(net):
            return Response({"error": "invalid lots"}, status=400)
        side = "Sell" if net > 0 else "Buy"

        # use latest mark as close price
        r = get_redis()
        mk = r.get(f"mark:{symbol}")
        if mk is None:
            return Response({"error": "no mark price available"}, status=503)
        price = float(mk)

        res = on_fill(request.user.id, symbol, side, close_lots, price)
        return Response({
            "ok": True,
            "symbol": symbol,
            "closed_lots": close_lots,
            "side": side,
            "price": price,
            "position": {
                "net_lots": res["new_net"],
                "avg_entry": res["new_avg"],
                "realized_pnl": res["realized"],
                "updated_at": res["updated_at"],
            }
        })


class OrderListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    def get_queryset(self):
        qs = Order.objects.filter(user_id=self.request.user.id).order_by("-created_at")
        symbol = self.request.query_params.get("symbol")
        return qs.filter(symbol=symbol) if symbol else qs

class FillListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FillSerializer
    def get_queryset(self):
        qs = Fill.objects.filter(user_id=self.request.user.id).order_by("-ts")
        symbol = self.request.query_params.get("symbol")
        return qs.filter(symbol=symbol) if symbol else qs


class MarginCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        symbol = request.data.get("symbol")
        lots = Decimal(request.data.get("lots", "0"))
        price = Decimal(request.data.get("price", "0"))

        try:
            # Fetch the UserAccount explicitly
            account = UserAccount.objects.get(user=request.user)
        except UserAccount.DoesNotExist:
            return Response({"ok": False, "error": "User account not found."}, status=400)

        # You may want to get leverage from request or from account if exists
        leverage = int(request.data.get("leverage", 500))  # Default leverage if none provided

        spec = spec_for(symbol)
        result = validate_order(account, lots, price, spec.contract_size, leverage)
        return Response(result)


class ExitPositionAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, *args, **kwargs):
        # KEEP THIS LOGIC
        user = request.user
        position_id = request.data.get("position_id")
        exit_price = request.data.get("exit_price")
        if not position_id or exit_price is None:
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = exit_position(user.id, position_id, float(exit_price))
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(res, status=status.HTTP_200_OK)


class CapitalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            account = UserAccount.objects.get(user=request.user)
            equity = account.balance + account.unrealized_pnl
            free_margin = equity - account.used_margin
            return Response({
                "balance": float(account.balance),
                "equity": float(equity),
                "used_margin": float(account.used_margin),
                "free_margin": float(free_margin),
            })
        except UserAccount.DoesNotExist:
            return Response({"error": "User account not found"}, status=404)


class OrderHistoryView(generics.ListAPIView):
    serializer_class = ClosedTradeSerializer
    permission_classes = [permissions.IsAuthenticated]


    def get_queryset(self):
        uid = self.request.user.id
        return (
            LedgerEntry.objects
            .filter(user_id=uid, kind="realized_pnl")
            .exclude(ref__isnull=True).exclude(ref="")
            .values("ref", "symbol")
            .annotate(
                realized=Sum("amount"),  # sum realized PnL
                last_ts=Max("ts"),       # <-- use ts, not created_at
            )
            .order_by("-last_ts")
        )


class OrderHistoryLastFillView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FillSerializer

    def get_queryset(self):
        from django.db.models import Window
        from django.db.models.functions import RowNumber
        uid = self.request.user.id
        return (
            Fill.objects
            .filter(user_id=uid, order__position_id__isnull=False)
            .annotate(
                pos_id=F("order__position_id"),
                rn=Window(RowNumber(), partition_by=[F("order__position_id")], order_by=F("ts").desc()),
            ).filter(rn=1).order_by("-ts")
        )