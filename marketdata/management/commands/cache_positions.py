import uuid
from django.core.management.base import BaseCommand
from marketdata.engine.redis_ops import get_redis, k_pos, k_posidx, k_symidx
from marketdata.models import PositionSnapshot  # Adjust to your actual model import path


class Command(BaseCommand):
    help = "Populate Redis cache with all current positions"

    def handle(self, *args, **options):
        r = get_redis()

        count = 0
        for pos in PositionSnapshot.objects.all():
            uid = pos.user_id
            position_id = str(uuid.uuid4())  # Generate unique position ID (or use pos.pk if appropriate)
            key = k_pos(uid, position_id)

            r.hset(key, mapping={
                "symbol": pos.symbol,
                "net_lots": float(pos.net_lots),
                "avg_entry": float(pos.avg_entry),
                "unreal_pnl": float(pos.unreal_pnl),
                "margin": float(pos.margin),
                "mark": float(pos.mark),
                "updated_at": int(pos.ts.timestamp()),
            })

            # Add this position id to user position index
            r.sadd(k_posidx(uid), position_id)

            # Add user id to symbol index
            r.sadd(k_symidx(pos.symbol), uid)

            count += 1

        self.stdout.write(self.style.SUCCESS(f"Cached {count} positions in Redis."))
