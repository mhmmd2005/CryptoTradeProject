import os

import django
from django.core.asgi import get_asgi_application

# ۱. تنظیم محیط
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CryptoTradeProject__.settings')

# ۲. فراخوانی اولیه برای لود شدن مدل‌ها (این سدِ جلوی خطای AppRegistry را می‌شکند)
django.setup()
application = get_asgi_application()

# ۳. حالا ایمپورت‌های کانال‌ها (بعد از لود شدن کامل جنگو)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import Prediction.routing
import adminPanel.routing

# ۴. ترکیب مسیرها
combined_urlpatterns = (
        Prediction.routing.websocket_urlpatterns +
        adminPanel.routing.websocket_urlpatterns
)

# ۵. بازنویسی اپلیکیشن با لایه وب‌سوکت
application = ProtocolTypeRouter({
    "http": application,
    "websocket": AuthMiddlewareStack(
        URLRouter(combined_urlpatterns)
    ),
})
