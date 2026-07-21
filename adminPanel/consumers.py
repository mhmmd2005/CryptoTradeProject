import json
from decimal import Decimal
from adminPanel.utils import get_platform_liquidity_data
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


# کلاس اینکودر برای مدیریت Decimal
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class LiquidityConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "admin_liquidity_group"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        initial_data = await database_sync_to_async(get_platform_liquidity_data)()

        # استفاده از cls=CustomJSONEncoder به جای default=str
        await self.send(text_data=json.dumps({
            'status': 'success',
            'assets': initial_data
        }, cls=CustomJSONEncoder))

    async def broadcast_liquidity(self, event):
        # اینجا هم حتماً از cls استفاده کنید
        await self.send(text_data=json.dumps({
            'status': 'success',
            'assets': event['assets']
        }, cls=CustomJSONEncoder))
