# marketdata/streams/user_ws.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from marketdata.engine.redis_ops import positions_snapshot
from channels.db import database_sync_to_async


class UserStream(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or user.is_anonymous:
            await self.close()
            return
        self.uid = str(user.id)
        self.group = f"user_{self.uid}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        snap = positions_snapshot(self.uid)
        await self.send_json({"type": "positions_snapshot", "data": snap})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    # positions engine will send to this handler name
    async def positions_update(self, event):
        await self.send_json({"type": "positions_update", "data": event["data"]})


class CapitalConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or user.is_anonymous:
            await self.close()
            return
        self.uid = str(user.id)
        self.group = f"user_capital_{self.uid}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # Optionally send current capital on connect
        capital = await self.get_current_capital(self.uid)
        await self.send_json({"type": "capital", **capital})

    async def disconnect(self, code):
        
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def capital_update(self, event):
   
        await self.send_json({"type": "capital", **event["capital"]})


    @database_sync_to_async
    def get_current_capital(self, user_id):
        from marketdata.models import UserAccount
        acc = UserAccount.objects.get(user_id=user_id)
        equity = acc.balance + acc.unrealized_pnl  # no 'equity' field
        print(f"[CAPITAL CONSUMER FETCH] user={user_id} balance={acc.balance} equity={equity} used_margin={acc.used_margin} free_margin={acc.free_margin}")

        return {
            "balance": float(acc.balance),
            "equity": float(equity),
            "used_margin": float(acc.used_margin),
            "free_margin": float(acc.free_margin),  # access the property
        }