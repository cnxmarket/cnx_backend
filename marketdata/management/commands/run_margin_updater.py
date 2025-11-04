import json
import os
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from redis import from_url
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from marketdata.models import UserAccount
from marketdata.engine.redis_ops import k_symidx, k_posidx, k_pos
from marketdata.engine.margin_utils import aggregate_user_margin_and_pnl
from django.db import transaction
from collections import defaultdict

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

class Command(BaseCommand):
    help = "Recalculate margin usage & unrealized PnL on price update ticks"

    def handle(self, *args, **kwargs):
        r = from_url(REDIS_URL, decode_responses=True)
        ps = r.pubsub()
        ps.psubscribe("ticks:*")

        self.stdout.write(self.style.SUCCESS("Margin updater started."))
        ch = get_channel_layer()
        last_capital_send = {}

        for msg in ps.listen():
            if msg["type"] not in ("message", "pmessage"):
                continue

            try:
                tick_data = json.loads(msg["data"])
                symbol = tick_data["symbol"]
                mark_price = Decimal(str(tick_data["mid"]))
            except Exception as e:
                self.stderr.write(f"Invalid tick data: {e}")
                continue

            user_ids = r.smembers(k_symidx(symbol)) or set()

            for uid in user_ids:
                uid = str(uid)
                if uid in last_capital_send and time.time() - last_capital_send[uid] < 2.0:
                    continue

                position_ids = r.smembers(k_posidx(uid)) or set()
                all_positions = []
                for pos_id in position_ids:
                    pos_fields = r.hgetall(k_pos(uid, pos_id))
                    if not pos_fields:
                        continue
                    try:
                        all_positions.append({
                            "symbol": pos_fields.get("symbol", ""),
                            "side": pos_fields.get("side", "Buy"),
                            "open_price": Decimal(pos_fields.get("open_price") or pos_fields.get("avg_entry") or mark_price),
                            "lots": Decimal(pos_fields.get("net_lots", "0")),
                            "contract_size": int(pos_fields.get("contract_size", 100000)),
                            "leverage": int(pos_fields.get("leverage", 500)),
                        })
                    except Exception as ex:
                        self.stderr.write(f"Bad position data for user {uid}: {ex}")

                if not all_positions:
                    continue

                # --- Deduplicate/net by (symbol, side): only ONE position per {symbol, side}
                agg_positions = defaultdict(lambda: {
                    "symbol": None,
                    "side": None,
                    "open_price": None,
                    "lots": Decimal("0"),
                    "contract_size": 0,
                    "leverage": 0
                })
                for pos in all_positions:
                    key = (pos["symbol"], pos["side"])
                    if agg_positions[key]["symbol"] is None:
                        agg_positions[key].update(pos)
                    agg_positions[key]["lots"] += pos["lots"]
                netted_positions = [p for p in agg_positions.values() if p["lots"] != 0]
                # ---

                symbols = set(pos["symbol"] for pos in netted_positions)
                current_prices = {}
                for s in symbols:
                    if s == symbol:
                        current_prices[s] = mark_price
                    else:
                        price_str = r.get(f"last_price:{s}")
                        try:
                            price = Decimal(price_str) if price_str else None
                        except:
                            price = None
                        if price and price > 0:
                            current_prices[s] = price
                        else:
                            open_price_fallback = next((pos["open_price"] for pos in netted_positions if pos["symbol"] == s), None)
                            if open_price_fallback and open_price_fallback > 0:
                                current_prices[s] = open_price_fallback
                            else:
                                self.stderr.write(f"No valid price for symbol {s} for user {uid}, skipping margin calc for this symbol")

                valid_prices = {k: v for k, v in current_prices.items() if v is not None}

         
                total_used_margin, total_unrealized_pnl = aggregate_user_margin_and_pnl(netted_positions, valid_prices)

                try:
                    with transaction.atomic():
                        account = UserAccount.objects.select_for_update().get(user_id=uid)
                        account.used_margin = total_used_margin
                        account.unrealized_pnl = total_unrealized_pnl
                        account.save(update_fields=['used_margin', 'unrealized_pnl'])

                    equity = account.balance + total_unrealized_pnl
                    free_margin = equity - total_used_margin

                    capital_payload = {
                        "balance": float(account.balance),
                        "equity": float(equity),
                        "used_margin": float(total_used_margin),
                        "free_margin": float(free_margin),
                    }

                    async_to_sync(ch.group_send)(
                        f"user_capital_{uid}",
                        {"type": "capital.update", "capital": capital_payload}
                    )

                    last_capital_send[uid] = time.time()
                    self.stdout.write(f"Margin updater: capital update -> {uid} {capital_payload}")

                    if free_margin < 0:
                        async_to_sync(ch.group_send)(
                            f"user_{uid}",
                            {
                                "type": "margin_alert",
                                "data": {"message": "Margin call: free margin below zero","free_margin": str(free_margin)},
                            },
                        )
                        self.stderr.write(f"Margin CALL for user {uid}: free_margin={free_margin}")

                except UserAccount.DoesNotExist:
                    self.stderr.write(f"UserAccount not found for uid={uid}")
                except Exception as e:
                    self.stderr.write(f"Error updating margin for user {uid}: {e}")

        self.stderr.write("Margin updater stopped.")
