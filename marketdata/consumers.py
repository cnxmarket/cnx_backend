# backend/marketdata/consumers.py

import os
import json
import threading
import time
import ssl
import websocket

from django.conf import settings
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .streams.user_ws import UserStream, CapitalConsumer


# Redis: publish ticks and cache latest marks
from redis import from_url
r = from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)

# Routing imports
from django.urls import re_path
from django_channels_jwt_auth_middleware.auth import JWTAuthMiddlewareStack
from .streams.user_ws import UserStream  # ensure this file exists

HEARTBEAT_SEC = 20
_symbol_threads = {}

# Add BTCUSDT for weekend testing
SUPPORTED_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "BTCUSDT", "XAUUSD", "NZDUSD"]


class QuoteConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.symbol = self.scope["url_route"]["kwargs"]["symbol"].upper()
        self.group_name = f"quotes_{self.symbol}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "status", "message": f"subscribing {self.symbol}"})
        if "alltick" not in _symbol_threads:
            t = threading.Thread(target=start_alltick_ws, daemon=True)
            t.start()
            _symbol_threads["alltick"] = t

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def broadcast_tick(self, event):
        try:
            await self.send_json(event["tick"])
        except Exception:
            pass


def start_alltick_ws():
    ws_url = f"{settings.ALLTICK_BASE_WS}?token={settings.ALLTICK_API_KEY}"
    channel_layer = get_channel_layer()

    def on_open(ws):
        sub = {
            "cmd_id": 22002,
            "seq_id": 1,
            "trace": "multi_sub",
            "data": {"symbol_list": [{"code": s, "depth_level": 1} for s in SUPPORTED_SYMBOLS]},
        }
        ws.send(json.dumps(sub))

        def heartbeat():
            while True:
                time.sleep(HEARTBEAT_SEC)
                try:
                    ws.send(json.dumps({"cmd_id": 9999, "seq_id": 1, "trace": "heartbeat"}))
                except Exception:
                    break

        threading.Thread(target=heartbeat, daemon=True).start()

    def on_message(ws, message):
        try:
            payload = json.loads(message)
            if not isinstance(payload, dict) or "data" not in payload:
                return

            d = payload["data"]
            symbol = d.get("code")
            if symbol not in SUPPORTED_SYMBOLS:
                return

            bid = d["bids"][0]["price"] if d.get("bids") else None
            ask = d["asks"][0]["price"] if d.get("asks") else None

            # Zero-spread normalization and mid computation
            mid = None
            if getattr(settings, "ZERO_SPREAD", True) and bid is not None and ask is not None:
                mid = (float(bid) + float(ask)) / 2.0
                bid = mid
                ask = mid
            else:
                # derive a mid even if one side is missing
                mid = float(ask or bid or d.get("last_price") or 0.0)

            # Publish slim tick for positions engine and cache the latest mark
            try:
                r.publish(
                    f"ticks:{symbol}",
                    json.dumps({
                        "symbol": symbol,
                        "mid": float(mid),
                        "ts": int(d.get("tick_time", 0)) // 1000
                    }),
                )
                r.set(f"mark:{symbol}", float(mid))
            except Exception:
                pass

            tick = {
                "type": "tick",
                "symbol": symbol,
                "ts": int(d.get("tick_time", 0)) // 1000,  # ms → sec
                "bid": float(bid) if bid is not None else None,
                "ask": float(ask) if ask is not None else None,
                "last": float(ask if ask is not None else (bid if bid is not None else 0.0)),
            }

            # Broadcast to symbol group
            async_to_sync(channel_layer.group_send)(
                f"quotes_{symbol}",
                {"type": "broadcast.tick", "tick": tick},
            )
        except Exception:
            pass

    def on_close(ws, code, msg):
        time.sleep(3)
        start_alltick_ws()

    while True:
        try:
            wsa = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_close=on_close,
            )
            wsa.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
        except Exception:
            time.sleep(3)


# WebSocket routes (public quotes, JWT-protected user stream)
websocket_urlpatterns = [
    re_path(r"^ws/quotes/(?P<symbol>[A-Za-z0-9]+)/$", QuoteConsumer.as_asgi()),
    re_path(r"^ws/user/stream/$", JWTAuthMiddlewareStack(UserStream.as_asgi())),
    re_path(r"^ws/user/capital/$", JWTAuthMiddlewareStack(CapitalConsumer.as_asgi())),   #
]
