import logging
from decimal import Decimal

from django.core.cache import cache

logger = logging.getLogger(__name__)


def get_live_price(symbol):
    """
    خواندن قیمت از کش (Redis) با دقت بالا
    """
    cache_key = f"live_price_{symbol}"

    try:
        price = cache.get(cache_key)

        # 🛡️ چک کردن اینکه قیمت وجود داشته باشد و صفر یا خالی نباشد
        if price and str(price).strip() != "":
            return Decimal(str(price)).quantize(Decimal("0.00000001"))  # دقت تا 8 رقم اعشار

        logger.warning(f"Price for {symbol} not found in Redis or is empty.")
        return None
    except Exception as e:
        logger.error(f"Error reading price from Redis for {symbol}: {e}")
        return None
