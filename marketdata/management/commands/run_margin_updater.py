# marketdata/engine/run_margin_updater.py
import os
import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from redis import from_url
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from marketdata.models import UserAccount
from marketdata.engine.redis_ops import k_posidx, k_pos

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

SEND_COOLDOWN_SECS = 2.0        # throttle websocket pushes per user
SLEEP_BETWEEN_PASSES = 0.25     # main loop sleep


class Command(BaseCommand):
    help = "Aggregate used/unrealized from Redis positions and update UserAccount; no recompute here."

    def handle(self, *args, **opts):
        r = from_url(REDIS_URL, decode_responses=True)
        ch_layer = get_channel_layer()

        self.stdout.write(self.style.SUCCESS("Margin updater started (no recompute)."))

        last_push_at: dict[str, float] = {}

        try:
            while True:
                user_ids = list(UserAccount.objects.values_list("user_id", flat=True))
                now = time.time()

                for uid_int in user_ids:
                    uid = str(uid_int)

                    if uid in last_push_at and (now - last_push_at[uid]) < SEND_COOLDOWN_SECS:
                        continue

                    try:
                        # --- SUM WHAT THE ENGINE ALREADY COMPUTED ---
                        total_used_margin = Decimal("0")
                        total_unrealized = Decimal("0")

                        position_ids = r.smembers(k_posidx(uid)) or set()
                        for pos_id in position_ids:
                            pkey = k_pos(uid, pos_id)
                            pos = r.hgetall(pkey)
                            if not pos:
                                continue

                            m = pos.get("margin")
                            u = pos.get("unreal_pnl")

                            if m is not None:
                                try:
                                    total_used_margin += Decimal(str(m))
                                except Exception:
                                    pass
                            if u is not None:
                                try:
                                    total_unrealized += Decimal(str(u))
                                except Exception:
                                    pass

                        # --- Update only the persisted fields ---
                        with transaction.atomic():
                            acc = (
                                UserAccount.objects.select_for_update()
                                .get(user_id=uid_int)
                            )

                            acc.unrealized_pnl = total_unrealized
                            acc.used_margin = total_used_margin
                            acc.save(update_fields=["unrealized_pnl", "used_margin"])

                            # Compute (do not assign) equity/free for the payload
                            equity = (acc.balance or Decimal("0")) + acc.unrealized_pnl
                            free_margin = equity - acc.used_margin

                            capital_payload = {
                                "balance": float(acc.balance),
                                "equity": float(equity),
                                "used_margin": float(acc.used_margin),
                                "free_margin": float(free_margin),
                                "unrealized_pnl": float(acc.unrealized_pnl),
                            }

                        # --- Push to user websocket group ---
                        async_to_sync(ch_layer.group_send)(
                            f"user_{uid}",
                            {
                                "type": "capital_update",
                                "capital": capital_payload,
                            },
                        )
                        last_push_at[uid] = now

                        # Optional: margin call alert
                        if free_margin < 0:
                            async_to_sync(ch_layer.group_send)(
                                f"user_{uid}",
                                {
                                    "type": "margin_alert",
                                    "data": {
                                        "message": "Margin call: free margin below zero",
                                        "free_margin": str(free_margin),
                                    },
                                },
                            )
                            self.stderr.write(
                                f"Margin CALL for user {uid}: free_margin={free_margin}"
                            )

                    except UserAccount.DoesNotExist:
                        self.stderr.write(f"UserAccount not found for uid={uid}")
                    except Exception as e:
                        self.stderr.write(f"Error updating margin for user {uid}: {e}")

                time.sleep(SLEEP_BETWEEN_PASSES)

        except KeyboardInterrupt:
            self.stderr.write("Margin updater stopped by user.")
        except Exception as e:
            self.stderr.write(f"Margin updater crashed: {e}")
