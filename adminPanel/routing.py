from django.urls import path
from adminPanel import consumers

websocket_urlpatterns = [
    path('ws/admin/liquidity/', consumers.LiquidityConsumer.as_asgi()),
]