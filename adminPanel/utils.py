# adminPanel/utils.py
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from wallet.models import DollarWallet

# قوانین پله‌ای قفل بر اساس تعداد خطاهای انباشته شده
LOCK_RULES = [
    (3, timedelta(minutes=1)),  # ۳ خطا -> ۱ دقیقه قفل
    (6, timedelta(minutes=5)),  # ۶ خطا -> ۵ دقیقه قفل
    (9, timedelta(minutes=15)),  # ۹ خطا -> ۱۵ دقیقه قفل
    (12, timedelta(minutes=30)),  # ۱۲ خطا -> ۳۰ دقیقه قفل
]

# زمان ماندگاری شمارنده خطاها در حافظه (۲ ساعت) جهت پیوستگی گام‌های قفل
FAILED_ATTEMPTS_WINDOW_SECONDS = 7200


def get_client_ip(request):
    """استخراج دقیق و ایمن IP واقعی کلاینت"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def check_admin_lock(request, email=None):
    """
    🔒 بررسی وضعیت قفل پورتال بر اساس IP کلاینت و ایمیل هدف
    """
    ip = get_client_ip(request)
    now_ts = int(timezone.now().timestamp())

    # ۱. بررسی قفل بودن IP
    ip_lock_until = cache.get(f"admin_lock:ip:{ip}")
    if ip_lock_until and now_ts < ip_lock_until:
        return ip_lock_until

    # ۲. بررسی قفل بودن ایمیل ادمین (جلوگیری از بروت‌فورس هماهنگ با IPهای متغیر)
    if email:
        email_clean = email.lower().strip()
        email_lock_until = cache.get(f"admin_lock:email:{email_clean}")
        if email_lock_until and now_ts < email_lock_until:
            return email_lock_until

    return None


def register_failed_attempt(request, email=None):
    """
    ⚡ ثبت اتمیک تلاش ناموفق با تمدید پویای TTL جهت حفظ تاریخچه خطاها پس از انقضای قفل‌ها
    """
    ip = get_client_ip(request)
    now_ts = int(timezone.now().timestamp())

    # معین کردن کلیدهای کش برای IP و ایمیل
    attempts_key_ip = f"failed_attempts:ip:{ip}"
    email_clean = email.lower().strip() if email else None
    attempts_key_email = f"failed_attempts:email:{email_clean}" if email_clean else None

    # ۱. افزایش یا ثبت اتمیک شمارنده IP
    is_new_ip = cache.add(attempts_key_ip, 1, timeout=FAILED_ATTEMPTS_WINDOW_SECONDS)
    if is_new_ip:
        failed_attempts_ip = 1
    else:
        try:
            failed_attempts_ip = cache.incr(attempts_key_ip)
        except ValueError:
            cache.set(attempts_key_ip, 1, timeout=FAILED_ATTEMPTS_WINDOW_SECONDS)
            failed_attempts_ip = 1

    # ۲. افزایش یا ثبت اتمیک شمارنده ایمیل ادمین
    failed_attempts_email = 0
    if attempts_key_email:
        is_new_email = cache.add(attempts_key_email, 1, timeout=FAILED_ATTEMPTS_WINDOW_SECONDS)
        if is_new_email:
            failed_attempts_email = 1
        else:
            try:
                failed_attempts_email = cache.incr(attempts_key_email)
            except ValueError:
                cache.set(attempts_key_email, 1, timeout=FAILED_ATTEMPTS_WINDOW_SECONDS)
                failed_attempts_email = 1

    # تابع محلی برای استخراج هوشمند زمان قفل بر اساس تعداد خطاها
    def calculate_lock_duration(attempts):
        # بررسی قوانین اصلی
        for target_attempts, duration in LOCK_RULES:
            if attempts == target_attempts:
                return int(duration.total_seconds())
        # سوپاپ اطمینان برای بیش از ۱۲ خطا (هر ۳ خطای اضافه -> ۳۰ دقیقه قفل مجدد)
        if attempts > 12 and attempts % 3 == 0:
            return 1800
        return None

    lock_duration_ip = calculate_lock_duration(failed_attempts_ip)
    lock_duration_email = calculate_lock_duration(failed_attempts_email) if email_clean else None

    # ۳. اعمال قفل IP و تمدید طول عمر شمارنده آن
    if lock_duration_ip:
        unlock_time_ip = now_ts + lock_duration_ip
        cache.set(f"admin_lock:ip:{ip}", unlock_time_ip, timeout=lock_duration_ip)

        # تمدید حیاتی: تعداد خطاها تا زمان اتمام قفل + ۲ ساعت بعد از آن در حافظه می‌ماند
        new_ttl_ip = lock_duration_ip + FAILED_ATTEMPTS_WINDOW_SECONDS
        cache.set(attempts_key_ip, failed_attempts_ip, timeout=new_ttl_ip)

    # ۴. اعمال قفل ایمیل و تمدید طول عمر شمارنده آن
    if lock_duration_email and email_clean:
        unlock_time_email = now_ts + lock_duration_email
        cache.set(f"admin_lock:email:{email_clean}", unlock_time_email, timeout=lock_duration_email)

        new_ttl_email = lock_duration_email + FAILED_ATTEMPTS_WINDOW_SECONDS
        cache.set(attempts_key_email, failed_attempts_email, timeout=new_ttl_email)


def reset_failed_attempts(request, email=None):
    """پاکسازی کامل و اتمیک شمارنده‌ها و قفل‌ها پس از لاگین موفق کلاینت"""
    ip = get_client_ip(request)
    cache.delete(f"failed_attempts:ip:{ip}")
    cache.delete(f"admin_lock:ip:{ip}")
    if email:
        email_clean = email.lower().strip()
        cache.delete(f"failed_attempts:email:{email_clean}")
        cache.delete(f"admin_lock:email:{email_clean}")


def log_admin_activity(request, action, model_name=None, object_id=None, description=""):
    """ثبت دقیق لاگ‌های امنیتی تغییرات ادمین"""
    from .models import AdminLog

    AdminLog.objects.create(
        admin=getattr(request, 'admin_user', None),
        action=action,
        model_name=model_name,
        object_id=object_id,
        description=description,
        ip_address=get_client_ip(request)
    )


def get_platform_liquidity_data():
    """
    🪙 رادار محاسبات تراز مالی نقدینگی کل پلتفرم NexTrade (نسخه ۳ ستونه کاملاً شفاف)
    """
    cached_assets = cache.get('nex_trade_assets_data')
    if cached_assets:
        return cached_assets

    target_coins = [
        {'code': 'btc', 'name': 'Bitcoin', 'icon': 'btc', 'fallback_price': Decimal('65000.00')},
        {'code': 'eth', 'name': 'Ethereum', 'icon': 'eth', 'fallback_price': Decimal('3500.00')},
        {'code': 'trx', 'name': 'Tron', 'icon': 'trx', 'fallback_price': Decimal('0.14')},
        {'code': 'usdttrc20', 'name': 'Tether TRC-20', 'icon': 'usdt', 'fallback_price': Decimal('1.00')}
    ]

    live_prices = cache.get('nex_trade_live_prices')
    if not live_prices:
        live_prices = cache.get('nex_trade_last_known_prices') or {}

    platform_assets = []

    for coin in target_coins:
        coin_totals = DollarWallet.objects.filter(currency=coin['code']).aggregate(
            free_tokens=Sum('balance'),
            frozen_tokens=Sum('frozen_balance')
        )

        total_free = coin_totals['free_tokens'] or Decimal('0.000000')
        total_frozen = coin_totals['frozen_tokens'] or Decimal('0.000000')
        total_coin = total_free + total_frozen

        if coin['code'] == 'usdttrc20':
            price, change_pct, is_up = Decimal('1.00'), Decimal('0.00'), True
        else:
            coin_data = live_prices.get(coin['code'])
            if coin_data:
                price = Decimal(str(coin_data['price']))
                change_pct = Decimal(str(coin_data['change_pct']))
            else:
                price, change_pct = coin['fallback_price'], Decimal('0.00')

            is_up = change_pct >= 0

        total_balance = total_coin * price

        platform_assets.append({
            'code': 'usdt' if coin['code'] == 'usdttrc20' else coin['code'],
            'name': coin['name'],
            'icon': coin['icon'],
            'is_stable': coin['code'] == 'usdttrc20',
            'is_up': is_up,
            'raw_change': abs(change_pct),
            'raw_balance': total_balance,
            'raw_coin': total_coin,
            'change_pct': f"{abs(change_pct):,.2f}%",
            'total_balance': f"${total_balance:,.2f}",
            'free_coin': f"{total_free:,.6f}".rstrip('0').rstrip('.'),
            'frozen_coin': f"{total_frozen:,.6f}".rstrip('0').rstrip('.'),
            'total_coin': f"{total_coin:,.6f}".rstrip('0').rstrip('.')
        })

    cache.set('nex_trade_assets_data', platform_assets, timeout=5)
    return platform_assets
