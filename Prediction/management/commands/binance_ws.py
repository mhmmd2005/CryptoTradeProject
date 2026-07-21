import asyncio
import json

import websockets
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand

BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"


class Command(BaseCommand):
    help = "Start Binance WebSocket price stream"

    def handle(self, *args, **options):
        asyncio.run(self.run())

    async def run(self):
        channel_layer = get_channel_layer()

        while True:  # 🔁 reconnect loop
            try:
                async with websockets.connect(
                        BINANCE_WS,
                        ping_interval=20,
                        ping_timeout=20
                ) as ws:
                    self.stdout.write(self.style.SUCCESS("Binance WS connected"))

                    async for msg in ws:
                        data = json.loads(msg)

                        await channel_layer.group_send(
                            "prices",
                            {
                                "type": "send_price",
                                "symbol": data["s"],  # ← از خود بایننس
                                "price": data["p"]
                            }
                        )

            except Exception as e:
                self.stderr.write(f"WS error: {e}")
                await asyncio.sleep(5)
