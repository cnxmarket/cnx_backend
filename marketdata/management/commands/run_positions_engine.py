import json, os, time
from django.core.management.base import BaseCommand
from redis import from_url
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from marketdata.engine.redis_ops import (
    get_redis, k_symidx, mark_to_market, k_pos, k_posidx
)
from marketdata.contracts import spec_for

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

class Command(BaseCommand):
    help = "Run positions engine: subscribe ticks:* and mark positions to market"

    def handle(self, *args, **opts):
        r = from_url(REDIS_URL, decode_responses=True)
        ps = r.pubsub()
        ps.psubscribe("ticks:*")

        ch_layer = get_channel_layer()
        self.stdout.write(self.style.SUCCESS("Positions engine started."))

        last_send = {}

        for msg in ps.listen():
            if msg["type"] not in ("message", "pmessage"):
                continue

            try:
                tick = json.loads(msg["data"])
                symbol = tick["symbol"]
                mid = float(tick["mid"])
                ts = int(tick["ts"])
            except Exception:
                continue

            spec = spec_for(symbol)
            uids = r.smembers(k_symidx(symbol)) or set()
            
            if not uids:
                continue

            for uid in uids:
                # lev = spec.leverage_max
                position_ids = r.smembers(k_posidx(uid)) or set()

                for position_id in position_ids:
                    pos_fields = r.hgetall(k_pos(uid, position_id))
                    if not pos_fields:
                        continue

                    if pos_fields.get("symbol", "") != symbol:
                        continue

                    lev = int(pos_fields.get("leverage", spec.leverage_max))
                    res = mark_to_market(uid, position_id, mid, spec.contract_size, lev)

                    now = time.time()
                    key = (uid, position_id)

                    if now - last_send.get(key, 0) >= 0.1:
                        data = {
                            "id": position_id,
                            "symbol": symbol,
                            "mark": res.get("last_mark"),
                            "open_price": float(pos_fields.get("avg_entry", 0)),
                            "unreal_pnl": res.get("unreal_pnl"),
                            "margin": res.get("margin"),
                            "open_time": int(pos_fields.get("open_time") or pos_fields.get("updated_at", 0)),
                            "side": (
                                "Sell" if float(pos_fields.get("net_lots", 0)) < 0
                                else "Buy" if float(pos_fields.get("net_lots", 0)) > 0
                                else ""
                            ),
                            "net_lots": float(pos_fields.get("net_lots", 0)),
                            "ts": res.get("updated_at"),
                        }
                        
                        async_to_sync(ch_layer.group_send)(
                            f"user_{uid}",
                            {"type": "positions_update", "data": data}
                        )
                        
                        last_send[key] = now

        self.stderr.write("Positions engine stopped.")
