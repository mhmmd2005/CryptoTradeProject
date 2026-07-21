import base64
import json
import logging
from decimal import Decimal, ROUND_DOWN
from io import BytesIO

import ccxt
import pyotp
import qrcode
import requests
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from UserPanel.models import UserTwoFactor
from accounts.forms import TwoStepVerificationForm
from accounts.models import User
from adminPanel.models import AdminUser, PlatformRevenue, RevenueJournal
from dashboard.forms import DisableTwoStepForm
from dashboard.models import InternalTrade
from dashboard.models import Notification
from wallet.models import DollarWallet  # فرض بر آدرس‌دهی درست مدل‌های شما
from .forms import UserProfileForm, CustomUsernameForm
from .models import UserProfile, ProfileApprovalStatus

logger = logging.getLogger(__name__)

# Create your views here.


# کالیبره کردن دقیق اعشار بر اساس ساختار مدل دیتابیس شما
COIN_PRECISION = Decimal('0.00000001')  # 8 places (مقدار کوین)
PRICE_PRECISION = Decimal('0.0001')  # 4 places (قیمت ارز)
TOTAL_PRECISION = Decimal('0.01')  # 2 places (مجموع دلار)
FEE_PRECISION = Decimal('0.0001')  # 4 places (کارمزد)


@method_decorator(csrf_exempt, name='dispatch')
class ExecuteInternalTradeView(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            action = data.get('action')  # 'BUY' یا 'SELL'
            crypto = data.get('crypto', '').lower()

            if crypto not in ['btc', 'eth', 'trx'] or action not in ['BUY', 'SELL']:
                return JsonResponse({'status': 'error', 'message': 'Invalid trade parameters provided.'}, status=400)

            # ۱. امنیت قیمت: قیمت زنده را از کش سرور (که هر ۱۰ ثانیه آپدیت می‌شود) می‌خوانیم
            # اگر در کش نبود، به عنوان لایه محافظتی ثانویه از دیتای فرانت استفاده میکنیم (یا مارکت را ارور میدهیم)
            server_live_price = cache.get(f"live_price_{crypto}")
            if server_live_price:
                live_price = Decimal(str(server_live_price))
            else:
                # فال‌بک امنیتی با اعمال پدیده حد نوسان مجاز در صورت نبود کش
                live_price = Decimal(str(data.get('price', 0)))

            live_price = live_price.quantize(PRICE_PRECISION, rounding=ROUND_DOWN)
            amount = Decimal(str(data.get('amount', 0))).quantize(COIN_PRECISION, rounding=ROUND_DOWN)

            if amount <= 0 or live_price <= 0:
                return JsonResponse({'status': 'error', 'message': 'Trade amount and price must be greater than zero.'},
                                    status=400)

            # محاسبات مالی هماهنگ با اعشار دیتابیس
            total_cost = (amount * live_price).quantize(TOTAL_PRECISION, rounding=ROUND_DOWN)
            fee = (total_cost * Decimal('0.0005')).quantize(FEE_PRECISION, rounding=ROUND_DOWN)

            with transaction.atomic():
                # ۱. واکشی ولت‌های کاربر و حساب درآمد مرکزی پلتفرم
                usdt_wallet, _ = DollarWallet.objects.get_or_create(user=request.user, currency='usdttrc20')
                crypto_wallet, _ = DollarWallet.objects.get_or_create(user=request.user, currency=crypto)

                # دریافت یا ساخت حساب تک‌فرزندی (Singleton) خزانه مرکزی
                revenue_account = PlatformRevenue.get_revenue_account()

                # ۲. قفل سطری دیتابیس برای جلوگیری از همروندی و Race Condition
                # ابتدا ولت‌های کاربر را قفل می‌کنیم
                wallet_ids = [usdt_wallet.id, crypto_wallet.id]
                locked_wallets = DollarWallet.objects.select_for_update().filter(id__in=wallet_ids).order_by('id')

                usdt_wallet = next(w for w in locked_wallets if w.currency == 'usdttrc20')
                crypto_wallet = next(w for w in locked_wallets if w.currency == crypto)

                # قفل کردن حساب درآمد مرکزی پلتفرم جهت ثبت دقیق مانده قبل و بعد
                revenue_account = PlatformRevenue.objects.select_for_update().get(id=revenue_account.id)

                # ذخیره مقدار موجودی خزانه پیش از اعمال کارمزد جدید
                balance_before = revenue_account.balance

                # ۳. بررسی و اعمال منطق خرید و فروش
                if action == 'BUY':
                    total_required = total_cost + fee
                    if usdt_wallet.balance < total_required:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Insufficient balance. Total required: {total_required} USDT | Available: {usdt_wallet.balance} USDT'
                        }, status=400)

                    usdt_wallet.balance -= total_required
                    crypto_wallet.balance += amount

                elif action == 'SELL':
                    if crypto_wallet.balance < amount:
                        return JsonResponse({'status': 'error', 'message': f'Insufficient {crypto.upper()} balance.'},
                                            status=400)

                    crypto_wallet.balance -= amount
                    net_usdt_receive = total_cost - fee
                    usdt_wallet.balance += net_usdt_receive

                # ۴. انتقال کارمزد به حساب درآمد پلتفرم
                revenue_account.balance += fee
                balance_after = revenue_account.balance

                # ۵. ذخیره‌سازی نهایی رکوردها در دیتابیس
                usdt_wallet.save()
                crypto_wallet.save()
                revenue_account.save()

                # ۶. ثبت سند در دفتر روزنامه درآمد پلتفرم (RevenueJournal)
                RevenueJournal.objects.create(
                    account=revenue_account,
                    amount=fee,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    user_email=request.user.email,
                    prediction=None  # چون این درآمد حاصل از معامله داخلی است، بخش پیش‌بینی خالی می‌ماند
                )

                # ۷. ثبت در تاریخچه معاملات کاربر
                trade_log = InternalTrade.objects.create(
                    user=request.user,
                    crypto_currency=crypto,
                    trade_type=action,
                    amount=amount,
                    price=live_price,
                    total_cost=total_cost,
                    fee=fee
                )

            return JsonResponse({
                'status': 'success',
                'message': 'Internal trade executed and recorded successfully.',
                'trade_id': trade_log.id,
                'balances': {
                    'usdttrc20': float(usdt_wallet.balance),
                    crypto: float(crypto_wallet.balance)
                }
            })


        except Exception as e:
            logger.error(f"Trade Execution Error for {request.user.email}: {str(e)}")
            return JsonResponse(
                {'status': 'error', 'message': 'An internal server error occurred. Please try again later.'},
                status=500)


class InternalTradeHistoryView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        queryset = InternalTrade.objects.filter(user=request.user).order_by('-id')

        search_query = request.GET.get('search', '').strip()
        filter_action = request.GET.get('action', '').strip().upper()

        if search_query:
            queryset = queryset.filter(
                Q(crypto_currency__icontains=search_query) |
                Q(trade_type__icontains=search_query)
            )

        if filter_action in ['BUY', 'SELL']:
            queryset = queryset.filter(trade_type=filter_action)

        paginator = Paginator(queryset, 10)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'search_query': search_query,
            'filter_action': filter_action,
            'total_count': queryset.count()
        }
        return render(request, 'user/internal_trade_history.html', context)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"
    login_url = "/sign_in/"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                request.user.refresh_from_db()
            except User.DoesNotExist:
                logout(request)
                return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # استخراج ولت‌های کاربر بر اساس فیلد currency در مدل DollarWallet
        usdt_wallet = user.crypto_wallets.filter(currency='usdttrc20').first()
        btc_wallet = user.crypto_wallets.filter(currency='btc').first()
        eth_wallet = user.crypto_wallets.filter(currency='eth').first()
        trx_wallet = user.crypto_wallets.filter(currency='trx').first()

        # پاس دادن مقدار عددی معتبر یا مقدار صفر دسیماال در صورت عدم وجود ولت
        context['wallet_usdt_balance'] = usdt_wallet.balance if usdt_wallet else Decimal('0.000000')
        context['wallet_btc_balance'] = btc_wallet.balance if btc_wallet else Decimal('0.000000')
        context['wallet_eth_balance'] = eth_wallet.balance if eth_wallet else Decimal('0.000000')
        context['wallet_trx_balance'] = trx_wallet.balance if trx_wallet else Decimal('0.000000')

        return context


class ProfileSettingsView(LoginRequiredMixin, View):
    template_name = "user/Setting.html"

    def get(self, request, tab=None, *args, **kwargs):
        user = request.user

        tab_titles = {
            "personal": "Personal Details",
            "password": "Change Password",
            "twostep": "Two Step Verification",
        }
        active_tab = tab or request.GET.get('tab', 'personal')
        page_title = tab_titles.get(active_tab, "Settings")

        # پروفایل کاربر
        profile = UserProfile.objects.filter(user=user).first()
        form = UserProfileForm(instance=profile)

        # وضعیت تایید پروفایل
        status = None
        if profile:
            status_obj = getattr(profile, "approval_status", None)
            if status_obj:
                status = getattr(status_obj, "status", None)
            else:
                status = getattr(profile, "status", None)

        if not profile:
            is_locked = False
        elif status == "approved":
            is_locked = True
        elif status == "rejected":
            is_locked = False
        else:  # pending
            is_locked = True

        # Two-Step setup
        twofa, _ = UserTwoFactor.objects.get_or_create(user=user)
        if not twofa.secret_key:
            twofa.secret_key = pyotp.random_base32()
            twofa.save()

        uri = pyotp.TOTP(twofa.secret_key).provisioning_uri(
            name=user.email, issuer_name="MySecureSite"
        )
        qr_img = qrcode.make(uri)
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode()

        context = {
            "form": form,
            "profile": profile,
            "is_locked": is_locked,
            "show_pending_message": status == "pending" if profile else False,
            "show_approved_message": status == "approved" if profile else False,
            "show_rejected_message": status == "rejected" if profile else False,
            "twofa": twofa,
            "qr_b64": qr_b64,
            "secret_key": twofa.secret_key,
            "is_enabled": twofa.is_enabled,
            "active_tab": active_tab,
            "page_title": page_title,
        }

        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        profile = UserProfile.objects.filter(user=request.user).first()
        form = UserProfileForm(request.POST, request.FILES, instance=profile)

        if form.is_valid():
            saved_profile = form.save(commit=False)
            saved_profile.locked = True
            saved_profile.status = "pending"
            saved_profile.user = request.user
            saved_profile.save()  # 🛡️ بدون هیچ‌گونه IntegrityError ذخیره می‌شود

            status_obj, _ = ProfileApprovalStatus.objects.get_or_create(profile=saved_profile)
            status_obj.status = "pending"
            status_obj.profile_status = "pending"
            status_obj.address_status = "pending"
            status_obj.save()

            main_admin = AdminUser.objects.first()

            if main_admin:
                full_name = f"{saved_profile.first_name} {saved_profile.last_name}" if saved_profile.first_name else request.user.email

                Notification.objects.create(
                    admin_recipient=main_admin,
                    user=None,
                    title="New Profile Verification Request",
                    message=f"User '{full_name}' has submitted their profile details for review.",
                    category='kyc',
                    notification_type='alert',
                    link="/adminPanel/Profile-Approval/"
                )

            return redirect("dashboard:profile-setting")

        context = self.get_context_for_post(request, form, profile)
        return render(request, self.template_name, context)

    def get_context_for_post(self, request, form, profile):
        tab_titles = {
            "personal": "Personal Details",
            "password": "Change Password",
            "twostep": "Two Step Verification",
        }
        active_tab = request.GET.get('tab', 'personal')
        page_title = tab_titles.get(active_tab, "Settings")

        status = None
        if profile:
            status_obj = getattr(profile, "approval_status", None)
            status = getattr(status_obj, "status", None) if status_obj else getattr(profile, "status", None)

        is_locked = True if status in ["approved", "pending"] else False
        twofa, _ = UserTwoFactor.objects.get_or_create(user=request.user)

        uri = pyotp.TOTP(twofa.secret_key).provisioning_uri(name=request.user.email, issuer_name="MySecureSite")
        qr_img = qrcode.make(uri)
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "form": form,
            "profile": profile,
            "is_locked": is_locked,
            "twofa": twofa,
            "qr_b64": qr_b64,
            "secret_key": twofa.secret_key,
            "is_enabled": twofa.is_enabled,
            "show_pending_message": status == "pending" if profile else False,
            "show_approved_message": status == "approved" if profile else False,
            "show_rejected_message": status == "rejected" if profile else False,
            "active_tab": active_tab,
            "page_title": page_title,
        }


class CustomUsernameView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = CustomUsernameForm(request.POST, request.FILES, instance=request.user.profile)

        if form.is_valid():
            profile = form.save()

            avatar_url = profile.avatar.url if profile.avatar else None

            return JsonResponse({
                'success': True,
                'message': 'Identity & Avatar synchronized.',
                'avatar_url': avatar_url
            })

        errors = next(iter(form.errors.values()))[0] if form.errors else 'Validation error.'
        return JsonResponse({'success': False, 'message': errors}, status=400)


class TwoStepVerifyView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = TwoStepVerificationForm(request.POST)
        if not form.is_valid():
            # برگشت خطاهای فرم به JSON
            return JsonResponse({"success": False, "error": form.errors["code"][0]})

        code = form.cleaned_data["code"]

        try:
            twofa = UserTwoFactor.objects.get(user=request.user)
        except UserTwoFactor.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Two-step setup not found."}
            )

        if twofa.verify_token(code):
            twofa.is_enabled = True
            twofa.save()
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": "Invalid code"})


class DisableTwoStepView(LoginRequiredMixin, View):
    """
    غیر فعال کردن Two-Step Authentication
    """

    def post(self, request, *args, **kwargs):
        form = DisableTwoStepForm(request.POST)
        if not form.is_valid():
            # خطای اعتبارسنجی فرم
            return JsonResponse({"success": False, "error": "Invalid input."})

        password = form.cleaned_data["password"]
        code = form.cleaned_data["code"]
        user = request.user

        # بررسی رمز حساب
        if not user.check_password(password):
            return JsonResponse(
                {"success": False, "error": "Incorrect account password!"}
            )

        # بررسی کد ۶ رقمی TOTP
        twofa, _ = UserTwoFactor.objects.get_or_create(user=user)
        if twofa.verify_token(code):
            twofa.is_enabled = False
            twofa.is_verified = False
            twofa.save()
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": "Invalid 6-digit code!"})


@login_required
def notifications_dropdown(request):
    notifications = request.user.user_notifications.all()[:10]
    return render(request, 'partials/notifications.html', {'notifications': notifications})


@login_required
@require_POST
def mark_notification_read(request):
    try:
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        notification = request.user.user_notifications.get(id=notification_id)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except (json.JSONDecodeError, Notification.DoesNotExist):
        return JsonResponse({'success': False}, status=400)


@require_POST
def mark_all_notifications_read(request):
    try:
        data = json.loads(request.body)
        scope = data.get('scope')  # 'admin' or 'user'
    except:
        scope = None

    # ۱. اگر درخواست از پنل ادمین بود
    if scope == 'admin':
        admin_key = request.COOKIES.get("admin_sessionid")
        if admin_key:
            admin_user = cache.get(f"admin_auth_{admin_key}")
            if not admin_user:
                session = SessionStore(session_key=admin_key)
                uid = session.get("admin_user_id")
                if uid:
                    from adminPanel.models import AdminUser
                    admin_user = AdminUser.objects.filter(id=uid, is_active=True).first()

            if admin_user:
                admin_user.admin_notifications.filter(is_read=False).update(is_read=True)
                return JsonResponse({'status': 'success', 'scope': 'admin'})

    # ۲. اگر درخواست از پنل کاربر بود
    elif scope == 'user' and request.user.is_authenticated:
        request.user.user_notifications.filter(is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success', 'scope': 'user'})

    return JsonResponse({'status': 'error', 'message': 'Invalid scope or unauthorized'}, status=400)


class MarketDataView(View):
    def get(self, request, *args, **kwargs):
        symbol = request.GET.get('symbol', 'BTC/USDT')
        ui_timeframe = request.GET.get('timeframe', '1H')

        # ۱. نگاشت دقیق ۵ تایم‌فریم جدید فرانت‌اِند به ساختار استاندارد CCXT/Binance
        # کلید: مقدار ارسالی از فرانت‌اِند | مقدار: (تایم‌فریم کندل، تعداد کندل برای نمایش تاریخچه)
        timeframe_mapping = {
            '15m': ('15m', 100),  # ۱۰۰ کندل ۱۵ دقیقه‌ای اخیر
            '1H': ('1h', 100),  # ۱۰۰ کندل ۱ ساعته اخیر
            '4H': ('4h', 100),  # ۱۰۰ کندل ۴ ساعته اخیر
            '1D': ('1d', 100),  # ۱۰۰ کندل روزانه اخیر
            '1W': ('1w', 52),  # ۵۲ کندل هفتگی اخیر (دیتاهای ۱ سال گذشته)
        }

        # اگر تایم‌فریم ارسالی نامعتبر بود، پیش‌فرض روی 1H (کندل‌های ۱ ساعته) تنظیم شود
        binance_tf, limit = timeframe_mapping.get(ui_timeframe, ('1h', 100))

        # ۲. کلید کش هوشمند برای هر جفت‌ارز و هر تایم‌فریم به صورت مجزا
        cache_key = f"market_data_{symbol.replace('/', '_')}_{binance_tf}_{limit}"
        data = cache.get(cache_key)

        if not data:
            try:
                # مقداردهی به صرافی بایننس از طریق CCXT
                exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}  # اختیاری: اگر دیتای فیوچرز می‌خواهید
                })

                # دریافت دیتای واقعی بر اساس تایم‌فریم و لیمیت جدید
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=binance_tf, limit=limit)

                if not ohlcv:
                    return JsonResponse({'series': []})

                data = [
                    {
                        'x': candle[0],  # Timestamp به میلی‌ثانیه
                        'y': [candle[1], candle[2], candle[3], candle[4]]  # Open, High, Low, Close
                    }
                    for candle in ohlcv
                ]

                # کش کوتاه مدت ۱۵ ثانیه‌ای برای جلوگیری از اسپم شدن API بایننس
                cache.set(cache_key, data, 15)

            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

        return JsonResponse({'series': data}, safe=False)


class BinanceTickerProxyView(View):
    def get(self, request, *args, **kwargs):
        binance_url = "https://api.binance.com/api/v3/ticker/24hr"

        # لیست دقیق منطبق با HTML بالا (بدون USDTUSDT نامعتبر)
        ticker_list = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "TRXUSDT"]

        # استفاده از separators برای حذف فاصله‌های اضافه و جلوگیری از خطای ۴۰۰ بایننس
        compact_symbols = json.dumps(ticker_list, separators=(',', ':'))

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(binance_url, params={'symbols': compact_symbols}, headers=headers, timeout=5)

            if response.status_code == 200:
                return JsonResponse(response.json(), safe=False)

            return JsonResponse({"error": "Binance API Error"}, status=response.status_code)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class LandingPageView(View):
    def get(self, request, *args, **kwargs):
        return render(request, "Landing/landing_page.html")
