import asyncio
import logging
import time
import traceback

import aiohttp
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.core.management.base import BaseCommand

# 🛡️ مطمئن شوید نام اپلیکیشن و مدل شما دقیقاً همین است
from Prediction.models import Asset

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Optimized Binance Price Feeder'

    def handle(self, *args, **options):
        """🚀 نقطه ورود رسمی جنگو - انتقال پروسس به محیط ناهمگام Async"""
        self.stdout.write(self.style.SUCCESS("🚀 Optimized Asynchronous Price Feeder started..."))
        try:
            asyncio.run(self.fetch_prices_loop())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n🛑 Feeder stopped by user."))

    async def fetch_prices_loop(self):
        TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
        channel_layer = get_channel_layer()

        # کش کردن لیست ارزها در حافظه لوکال اسکریپت برای کاهش فشار روی DB
        cached_assets = []
        last_db_sync = 0

        async with aiohttp.ClientSession() as session:
            while True:
                # به‌روزرسانی لیست ارزها از دیتابیس فقط هر 60 ثانیه یک‌بار
                if time.time() - last_db_sync > 60:
                    cached_assets = await self.get_assets_from_db()
                    last_db_sync = time.time()

                if not cached_assets:
                    self.stdout.write(self.style.WARNING("⚠️ No assets found in database. Waiting 5s..."))
                    await asyncio.sleep(5)
                    continue

                try:
                    async with session.get(TICKER_URL, timeout=5) as response:
                        if response.status != 200:
                            self.stdout.write(self.style.WARNING(f"✘ Binance API Error: {response.status}"))
                            await asyncio.sleep(2)
                            continue

                        data = await response.json()
                        # تبدیل لیست به دیکشنری برای دسترسی O(1) و سرعت ماکزیمم
                        all_prices = {item['symbol']: item['price'] for item in data}

                    now_ts = time.time()
                    for asset_symbol in cached_assets:
                        symbol_pair = f"{asset_symbol}USDT"
                        price_str = all_prices.get(symbol_pair)

                        if price_str:
                            price = float(price_str)

                            # ۱. آپدیت قیمت زنده برای استفاده در بخش‌های عمومی سایت
                            cache.set(f"live_price_{asset_symbol}", price, 60)

                            # ۲. 💎 ذخیره‌سازی در Redis Sorted Set برای تسویه حساب‌های دقیق ثانیه‌ای
                            redis_conn = cache.client.get_client()
                            key = f"price_history_{asset_symbol}"
                            redis_conn.zadd(key, {str(price): now_ts})

                            # پاکسازی دیتای قدیمی‌تر از 60 ثانیه برای سبک ماندن حافظه RAM رادیس
                            redis_conn.zremrangebyscore(key, 0, now_ts - 60)

                            # ۳. انتشار قیمت زنده روی کانال وب‌ساکت کلاینت‌ها
                            await channel_layer.group_send("round_updates", {
                                "type": "price_update",
                                "symbol": asset_symbol,
                                "price": price_str
                            })

                            # لاگ وضعیت در ترمینال برای مانیتورینگ شما
                            self.stdout.write(self.style.SUCCESS(f"✔ {asset_symbol}: {price_str}"))
                        else:
                            self.stdout.write(self.style.WARNING(f"✘ Symbol {symbol_pair} not found on Binance!"))

                    await asyncio.sleep(0.8)

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Feeder Loop Error: {e}"))
                    logger.error(f"Feeder Error: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(2)

    @sync_to_async
    def get_assets_from_db(self):
        """خواند امن و Non-blocking دیتابیس در محیط کاملاً Async"""
        try:
            return list(Asset.objects.all().values_list('symbol', flat=True))
        except Exception as db_err:
            logger.error(f"Failed to fetch assets from DB: {db_err}")
            return []
