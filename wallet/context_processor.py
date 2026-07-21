# context_processor.py
from django.urls import resolve


def breadcrumb_context(request):
    path = request.path
    view_name = resolve(path).url_name  # نام view فعلی
    # می‌توان مسیر URL را تقسیم کرد و نام‌ها را ساخت
    parts = path.strip('/').split('/')
    breadcrumb = []
    for i, part in enumerate(parts):
        breadcrumb.append({
            "title": part.replace('-', ' ').capitalize(),
            "url": '/' + '/'.join(parts[:i + 1]) + '/'
        })
    # آخرین آیتم بدون لینک
    if breadcrumb:
        breadcrumb[-1]['url'] = None
    return {"breadcrumb": breadcrumb}


def wallet_context(request):
    if request.user.is_authenticated:
        try:
            # ⚡ اصلاح: استفاده از related_name درست و فیلتر کردن روی ارز مشخص
            # از آنجا که ولت‌ها لیست هستند، از first() استفاده می‌کنیم
            user_wallet = request.user.crypto_wallets.filter(currency="usdttrc20").first()
            return {'wallet': user_wallet}
        except Exception as e:
            print(f"DEBUG: Wallet Context Error: {e}")
            return {'wallet': None}
    return {'wallet': None}
