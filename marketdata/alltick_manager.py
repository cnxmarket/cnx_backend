import json, threading, time, ssl, asyncio
import websocket   # websocket-client
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from redis import from_url
import os, json

r = from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)

HEARTBEAT_SEC = 20

class AlltickManager:
    _instances = {}

    def __init__(self, symbol):
        self.symbol = symbol
        self.channel_layer = get_channel_layer()
        self.group_name = f"quotes_{symbol}"
        self.thread = None
        self.running = False

    @classmethod
    def get_instance(cls, symbol):
        if symbol not in cls._instances:
            cls._instances[symbol] = AlltickManager(symbol)
            cls._instances[symbol].start()
        return cls._instances[symbol]

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_ws, daemon=True)
        self.thread.start()

    def _run_ws(self):
        ws_url = f"{settings.ALLTICK_BASE_WS}?token={settings.ALLTICK_API_KEY}"

        def on_open(ws):
            sub = {
                "cmd_id": 22002,
                "seq_id": 1,
                "trace": f"sub_{self.symbol}",
                "data": {"symbol_list": [{"code": self.symbol, "depth_level": 1}]}
            }
            ws.send(json.dumps(sub))

            def heartbeat():
                while self.running:
                    time.sleep(HEARTBEAT_SEC)
                    try:
                        ws.send(json.dumps({"cmd_id": 9999, "seq_id": 1, "trace": "heartbeat"}))
                    except Exception:
                        break
            threading.Thread(target=heartbeat, daemon=True).start()

        def on_message(ws, message):
            try:
                payload = json.loads(message)
                if isinstance(payload, dict) and "data" in payload and payload["data"]:
                    item = payload["data"][0]

                    tick = {
                        "type": "tick",
                        "symbol": item.get("symbol", self.symbol),
                        "ts": int(item.get("timestamp", 0)),  # keep your current ts
                        "bid": item.get("bidPrice"),
                        "ask": item.get("askPrice"),
                        "last": item.get("lastPrice"),
                    }

                    # --- ZERO-SPREAD NORMALIZATION (server-side) ---
                    try:
                        if getattr(settings, "ZERO_SPREAD", True) and tick["bid"] is not None and tick["ask"] is not None:
                            mid = (float(tick["bid"]) + float(tick["ask"])) / 2.0
                            tick["bid"] = mid
                            tick["ask"] = mid
                            tick["last"] = mid
                        else:
                            # derive a mid for publish even if one side is None
                            b = float(tick["bid"]) if tick["bid"] is not None else None
                            a = float(tick["ask"]) if tick["ask"] is not None else None
                            mid = (a + b) / 2.0 if a is not None and b is not None else float(tick["last"] or a or b or 0.0)
                    except Exception:
                        mid = float(tick["last"] or 0.0)
                    # --- END NORMALIZATION ---

                    # Broadcast to WS group (existing)
                    async_to_sync(self.channel_layer.group_send)(
                        self.group_name,
                        {"type": "broadcast.tick", "tick": tick}
                    )

                    # Publish a slim tick to Redis Pub/Sub for the positions engine
                    try:
                        r.publish(f"ticks:{tick['symbol']}", json.dumps({
                            "symbol": tick["symbol"],
                            "mid": mid,
                            "ts": tick["ts"],
                        }))
                    except Exception:
                        pass
            except Exception:
                pass


        def on_close(ws, code, msg):
            self.running = False
            time.sleep(3)
            self.start()  # auto-reconnect

        wsa = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_close=on_close
        )
        wsa.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
