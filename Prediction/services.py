# prediction/services.py
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django_redis import get_redis_connection
from Prediction.utils import get_live_price
from .models import Prediction
from .models import Prediction


def place_prediction(user, round_obj, amount: Decimal, direction: str):
    # چک کردن اولیه و سریع مقدار دسیماال
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Invalid amount")

    # بررسی وجود ریلیشن والت قبل از ورود به دیتابیس
    if not hasattr(user, "dollar_wallet") or user.dollar_wallet is None:
        raise ValueError("User has no wallet")

    with transaction.atomic():
        # 🛡️ ایمن‌سازی در برابر Race Condition: قفل کردن ردیف والت در دیتابیس تا پایان تراکنش
        wallet_model = user.dollar_wallet.__class__
        wallet = wallet_model.objects.select_for_update().get(id=user.dollar_wallet.id)

        if amount > wallet.balance:
            raise ValueError("Insufficient balance")

        # کسر موجودی و ذخیره امن
        wallet.balance -= amount
        wallet.save(update_fields=["balance"])

        # ثبت تراکنش مالی
        from wallet.models import WalletTransaction
        tx = WalletTransaction.objects.create(
            wallet=wallet,
            tx_hash=f"BET-{round_obj.id}-{user.id}-{int(timezone.now().timestamp())}",
            amount=amount,
            type="bet",
            status="success",
            confirmed=True,
            pay_address=""
        )

        # ثبت پیش‌بینی کاربر
        p = Prediction.objects.create(
            user=user,
            round=round_obj,
            amount=amount,
            direction=direction
        )

    return p


def get_historical_price(symbol, timestamp):
    """
    دریافت قیمت از تاریخچه ردیس (Sorted Set)
    دقیق‌ترین قیمت در لحظه مشخص شده را برمی‌گرداند.
    """
    try:
        # 🚀 استفاده از اتصال مستقیم و بهینه django_redis
        redis_conn = get_redis_connection("default")
    except Exception:
        redis_conn = cache.client.get_client()

    key = f"price_history_{symbol}"
    ts_val = timestamp.timestamp()

    try:
        # پیدا کردن نزدیک‌ترین قیمت ثبت شده در بازه زمانی کاندل (تا 2 ثانیه بعد از آن)
        result = redis_conn.zrangebyscore(key, ts_val, ts_val + 2, start=0, num=1)

        if result:
            return Decimal(result[0].decode('utf-8'))
    except Exception as redis_err:
        logger.error(f"Redis historical fetch failed for {symbol}: {redis_err}")

    # 🛡️ اگر به هر دلیلی دیتای تاریخچه نبود، سیستم متوقف نمی‌شود و قیمت زنده را جایگزین می‌کند
    return get_live_price(symbol)
