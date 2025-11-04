import json
from django.core.management.base import BaseCommand
from django.conf import settings
from redis import from_url

from marketdata.models import UserAccount
from marketdata.engine.redis_ops import k_posidx, k_pos

class Command(BaseCommand):
    help = "Check current positions and margin usage for user"

    def add_arguments(self, parser):
        parser.add_argument('user_id', nargs='?', type=int, default=1, help="User ID to check margin for")

    def handle(self, *args, **options):
        user_id = options.get('user_id', 1)
        
        print(f"Margin Check for User {user_id}")
        print("=" * 60)
        
        # Use the same Redis connection as the main system
        from marketdata.engine.redis_ops import get_redis
        r = get_redis()  # This will use your Django settings for REDIS_URL
        
        print(f"Connecting to Redis: {getattr(settings, 'REDIS_URL', 'redis://127.0.0.1:6379/0')}")
        
        try:
            # Get all user positions from Redis
            position_ids = r.smembers(f"posidx:{user_id}") or set()
            print(f"Found {len(position_ids)} position records")
            
            positions = []
            total_margin_used = 0.0
            
            if position_ids:
                for pos_id in position_ids:
                    pos_id_str = pos_id.decode() if isinstance(pos_id, bytes) else str(pos_id)
                    pos_key = f"pos:{user_id}:{pos_id_str}"
                    pos = r.hgetall(pos_key)
                    
                    if pos:
                        symbol = pos.get("symbol", "")
                        net_lots = float(pos.get("net_lots", 0))
                        margin = float(pos.get("margin", 0))
                        
                        # Only consider open positions with lots > 0
                        if abs(net_lots) > 0.000001:  # Small tolerance for tiny positions
                            try:
                                position_info = {
                                    "position_id": pos_id_str,
                                    "symbol": symbol,
                                    "net_lots": net_lots,
                                    "margin": margin,
                                    "open_price": float(pos.get("avg_entry", 0)),
                                    "mark": float(pos.get("last_mark", 0)),
                                }
                                positions.append(position_info)
                                total_margin_used += margin
                                print(f"  📊 {symbol}: {net_lots} lots, Margin: ${margin:.2f}")
                            except Exception as e:
                                print(f"    ❌ Error parsing position {pos_id}: {e}")
                                continue
            else:
                print("  No position index found in Redis")
                
        except Exception as e:
            print(f"  ❌ Redis connection failed: {e}")
            print("  Trying with default Redis URL...")
            try:
                r = from_url("redis://127.0.0.1:6379/0", decode_responses=True)
                position_ids = r.smembers(f"posidx:{user_id}") or set()
                if position_ids:
                    for pos_id in position_ids:
                        pos_id_str = pos_id.decode() if isinstance(pos_id, bytes) else str(pos_id)
                        pos_key = f"pos:{user_id}:{pos_id_str}"
                        pos = r.hgetall(pos_key)
                        if pos:
                            symbol = pos.get("symbol", "")
                            net_lots = float(pos.get("net_lots", 0))
                            margin = float(pos.get("margin", 0))
                            if abs(net_lots) > 0:
                                positions.append({
                                    "position_id": pos_id_str,
                                    "symbol": symbol,
                                    "net_lots": net_lots,
                                    "margin": margin,
                                    "open_price": float(pos.get("avg_entry", 0)),
                                    "mark": float(pos.get("last_mark", 0)),
                                })
                                total_margin_used += margin
                                print(f"  📊 {symbol}: {net_lots} lots, Margin: ${margin:.2f}")
            except Exception as e2:
                print(f"  ❌ All Redis attempts failed: {e2}")
                positions = []
                total_margin_used = 0.0
        
        # Get account details from database
        try:
            account = UserAccount.objects.get(user_id=user_id)
            account_equity = account.balance + account.unrealized_pnl
            account_free_margin = account_equity - account.used_margin
            
            print(f"\n💰 Account Information:")
            print(f"  Balance: ${float(account.balance):,.2f}")
            print(f"  Unrealized P&L: ${float(account.unrealized_pnl):,.2f}")
            print(f"  Equity: ${float(account_equity):,.2f}")
            print(f"  Total Used Margin: ${float(account.used_margin):,.2f}")
            print(f"  Free Margin: ${float(account_free_margin):,.2f}")
            
        except UserAccount.DoesNotExist:
            print(f"\n❌ No UserAccount found for user_id={user_id}")
            print(f"Cannot perform margin verification without account data.")
            return

        # Compare Redis vs Database margin
        print(f"\n🔍 Margin Verification:")
        print(f"  📊 Sum from Redis positions: ${total_margin_used:.2f}")
        print(f"  💰 UserAccount.used_margin: ${float(account.used_margin):,.2f}")
        
        margin_diff = total_margin_used - float(account.used_margin)
        if abs(margin_diff) <= 1.0:  # Allow $1 margin of error
            print("  ✅ Margin data consistent between Redis and Database")
        else:
            print(f"  ⚠️  Margin discrepancy: ${margin_diff:.2f}")

        # Margin capacity analysis
        print(f"\n📊 Margin Capacity Analysis:")
        if len(positions) > 0:
            avg_margin_per_pos = total_margin_used / len(positions)
            print(f"  Current positions: {len(positions)}")
            print(f"  Average margin per position: ${avg_margin_per_pos:.2f}")
            
            # Calculate how many $1000 margin positions could be opened
            additional_positions_at_1k = int(account_free_margin / 1000) if account_free_margin >= 1000 else 0
            total_positions_at_1k = len(positions) + additional_positions_at_1k
            
            print(f"  Current equity: ${float(account_equity):,.2f}")
            print(f"  Current used margin: ${float(account.used_margin):,.2f}")
            print(f"  Available margin: ${float(account_free_margin):,.2f}")
            print(f"  Max $1000-margin positions: {additional_positions_at_1k} more")
            print(f"  Total: {total_positions_at_1k} positions at $1000 margin each")
            
            if total_positions_at_1k < 10:
                margin_needed_for_10 = 10000 - float(account.used_margin)
                print(f"  ⚠️  To support 10 positions: need ${margin_needed_for_10:.2f} more margin")
            else:
                print(f"  ✅ Can support {total_positions_at_1k} positions at $1000 margin each")
                if total_positions_at_1k > 10:
                    print(f"  💰 Current setup supports more than 100% capacity")
            
            # Margin level calculation
            if float(account.used_margin) > 0:
                margin_level = (float(account_equity) / float(account.used_margin)) * 100
                print(f"Margin Level: {margin_level:.1f}%")
                
                if margin_level > 500:
                    print("  📈 Excellent margin buffer - very safe")
                elif margin_level > 200:
                    print("  ✅ Good margin level - comfortable buffer")
                elif margin_level > 100:
                    print("  ⚠️  Approaching margin call territory - be cautious")
                else:
                    print("  🚨 Margin call risk - immediate action may be needed")
            else:
                print("  Margin Level: N/A (no positions)")
                print("  📈 Full margin capacity available")
        else:
            print(f"\n📊 No open positions found")
            print(f"  💰 Total capital: ${float(account.balance):,.2f}")
            max_positions_at_1k = int(float(account.balance) / 1000)
            print(f"  📊 With $10,000 balance: can support {max_positions_at_1k} positions at $1000 margin each")
            print(f"  ✅ 10 positions at $1000 margin each: {'YES' if max_positions_at_1k >= 10 else 'NO'}")

        # Position list
        print(f"\n📋 Current Open Positions:")
        if positions:
            print("Symbol | Lots | Entry Price | Current Mark | Unrealized P&L | Margin Used")
            print("-" * 60)
            for pos in positions:
                mark = pos.get("mark", 0)
                entry = pos.get("open_price", 0)
                pnl = float(pos.get("unrealized_pnl", 0))
                lots = pos.get("net_lots", 0)
                margin = pos.get("margin", 0)
                
                print(f"{pos['symbol']} | {lots} | {entry} | {mark} | {pnl:+.2f} | ${margin:.2f}")
        else:
            print("No open positions found.")

        print(f"\n📊 Margin Summary:")
        print(f"  💰  Account balance: ${float(account.balance):,.2f}")
        print(f"  📈  Current equity: ${float(account_equity):,.2f}")
        print(f"  📊  Total used margin: ${float(account.used_margin):,.2f}")
        print(f"  🆓  Available margin: ${float(account_free_margin):,.2f}")
        print(f"  📝  Current positions: {len(positions)}")
        
        if float(account_free_margin) >= 1000:
            max_more_at_1k = int(float(account_free_margin) / 1000)
            print(f"  ✅  Can open: {max_more_at_1k} more positions at $1000 margin each")
        else:
            print(f"  ⚠️  Cannot open new $1000-margin positions")
            print(f"     Free margin available: ${float(account_free_margin):,.2f}")

