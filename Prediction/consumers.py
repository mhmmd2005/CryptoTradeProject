# Prediction/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer
import json

class RoundConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        # ۱. عضویت در گروه عمومی برای دریافت آپدیت راندها و قیمت‌ها
        await self.channel_layer.group_add("round_updates", self.channel_name)

        # ۲. عضویت در گروه اختصاصی کاربر (فقط اگر لاگین کرده باشد)
        if self.user.is_authenticated:
            self.user_group = f"user_updates_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # خارج شدن از گروه عمومی
        await self.channel_layer.group_discard("round_updates", self.channel_name)

        # خارج شدن از گروه اختصاصی
        if self.user.is_authenticated:
            user_group = f"user_updates_{self.user.id}"
            await self.channel_layer.group_discard(user_group, self.channel_name)

    async def round_update(self, event):
        """دریافت تغییرات تایم‌فریم راندها"""
        await self.send_json(event)

    async def price_update(self, event):
        """دریافت قیمت‌های زنده ارزها"""
        await self.send_json({
            "type": "price_update",
            "symbol": event["symbol"],
            "price": event["price"]
        })

    async def settlement_notification(self, event):
        """دریافت اعلان سود/ضرر (فقط برای این کاربر خاص)"""
        # فرستادن مستقیم دیتای تسویه حساب به فرانت‌اند
        await self.send_json(event)
