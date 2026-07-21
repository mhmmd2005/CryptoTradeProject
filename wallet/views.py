import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from wallet.signals import get_or_create_wallet_safely
from django.db.models.functions import TruncDay
from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from adminPanel.models import PlatformRevenue, RevenueJournal

from Prediction.models import Prediction
from UserPanel.models import UserTicket
from core.mixins import KYCRequiredMixin
from wallet.models import WalletTransaction, WithdrawRequest, DollarWallet, CurrencyConfig
from .forms import WithdrawForm

User = get_user_model()
logger = logging.getLogger("django")
logger = logging.getLogger(__name__)


class WalletWithdrawView(LoginRequiredMixin, KYCRequiredMixin, View):
    template_name = "wallet/buy-and-sell.html"

    def get(self, request):
        selected_currency = request.GET.get('currency', 'usdttrc20').lower()

        # جلوگیری از حلقه ریدایرکت با بکارگیری متد هوشمند get_or_create
        wallet, created = request.user.crypto_wallets.get_or_create(
            currency=selected_currency,
            defaults={
                'address': f"T{uuid.uuid4().hex[:33].upper()}",
                'private_key': 'encrypted_placeholder'
            }
        )

        # محاسبات آمار ولت
        total_dep = WalletTransaction.objects.filter(
            wallet=wallet, type='deposit', status__iexact='success'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.000000')

        total_wit = WithdrawRequest.objects.filter(
            wallet=wallet, status__iexact='done'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.000000')

        stats = {
            "total_deposits": float(total_dep),
            "total_withdraws": float(total_wit),
            "net_flow": float(total_dep - total_wit),
            "wallet_volume": float(total_dep + total_wit),
        }

        # نمودار ۷ روز گذشته بر اساس تدوام زمانی مبدا (timestamp)
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6)

        deposits_query = WalletTransaction.objects.filter(
            wallet=wallet, type='deposit', status__iexact='success', timestamp__date__gte=seven_days_ago
        ).annotate(date=TruncDate('timestamp')).values('date').annotate(daily_sum=Sum('amount'))

        withdraws_query = WithdrawRequest.objects.filter(
            wallet=wallet, status__iexact='done', created_at__date__gte=seven_days_ago
        ).annotate(date=TruncDate('created_at')).values('date').annotate(daily_sum=Sum('amount'))

        dep_dict = {item['date']: float(item['daily_sum']) for item in deposits_query}
        wit_dict = {item['date']: float(item['daily_sum']) for item in withdraws_query}

        categories, deposit_data, withdraw_data = [], [], []
        for i in range(7):
            current_date = seven_days_ago + timedelta(days=i)
            categories.append(current_date.strftime('%a'))
            deposit_data.append(dep_dict.get(current_date, 0.0))
            withdraw_data.append(wit_dict.get(current_date, 0.0))

        chart_data = {
            'categories': categories,
            'deposits': deposit_data,
            'withdraws': withdraw_data
        }

        configs = CurrencyConfig.objects.filter(is_active=True)
        configs_dict = {}
        for c in configs:
            configs_dict[c.code] = {
                'allow_auto_withdraw': c.allow_auto_withdraw,
                'auto_withdraw_limit': float(c.auto_withdraw_limit),
                'admin_review_limit': float(c.admin_review_limit),
                'fee_structure': c.fee_structure,
            }

        # پاس دادن آدرس ولت و نوع ارز به فرم جهت اعتبارسنجی لایه اول فرانت/بک
        withdraw_form = WithdrawForm(wallet_address=wallet.address, currency=selected_currency)
        transactions = wallet.transactions.select_related('withdraw').all().order_by("-timestamp")[:10]

        return render(request, self.template_name, {
            "wallet": wallet,
            "selected_currency": selected_currency,
            "wallet_address": wallet.address,
            "transactions": transactions,
            "withdraw_form": withdraw_form,
            "stats": stats,
            "chart_data_json": json.dumps(chart_data),
            "currency_configs_json": json.dumps(configs_dict),
        })

    def post(self, request):
        selected_currency = request.POST.get('currency', 'usdttrc20').lower()

        with transaction.atomic():
            try:
                wallet = request.user.crypto_wallets.select_for_update().get(currency=selected_currency)
            except DollarWallet.DoesNotExist:
                messages.error(request, "Target wallet not found.", extra_tags="withdraw")
                return redirect("buy-and-sell")

            form = WithdrawForm(wallet_address=wallet.address, currency=selected_currency, data=request.POST)

            if not form.is_valid():
                for field, errs in form.errors.items():
                    for err in errs:
                        messages.error(request, err, extra_tags="withdraw")
                return redirect(f"/my-wallet/?currency={selected_currency}")

            amount = form.cleaned_data["amount"]
            address = form.cleaned_data["address"]

            # 🌟 دریافت کانفیگ در ابتدای منطق (ضروری برای محاسبه کارمزد و چک‌های امنیتی)
            config = CurrencyConfig.objects.filter(code=selected_currency, is_active=True).first()
            if not config:
                messages.error(request, "Withdrawals for this asset are temporarily disabled.", extra_tags="withdraw")
                return redirect(f"/my-wallet/?currency={selected_currency}")

            # 🧮 محاسبه هوشمند کارمزد با متد جدید مدل
            fee = config.get_fee(amount)
            total_deduction = amount + fee

            # 💳 بررسی موجودی بر اساس مبلغ کل (اصل + کارمزد)
            if total_deduction > wallet.balance:
                messages.error(request,
                               f"Insufficient balance. Need {total_deduction} {wallet.currency_upper} (incl. {fee} fee).",
                               extra_tags="withdraw")
                return redirect(f"/my-wallet/?currency={selected_currency}")

            # --- منطق بررسی‌های KYC و مدیریت ریسک ---
            is_kyc_approved = (getattr(request.user, 'profile', None) and request.user.profile.status == 'approved')
            is_2fa_enabled = (getattr(request.user, 'two_factor', None) and request.user.two_factor.is_enabled)
            final_status = "pending"
            admin_note_text = ""

            if selected_currency in ['btc', 'eth']:
                final_status = "pending"
                admin_note_text = f"Strict Security Policy: 100% mandatory manual review required."
            elif not config.allow_auto_withdraw:
                final_status = "pending"
                admin_note_text = f"Security Policy: 100% manual review required."
            else:
                if amount < config.auto_withdraw_limit:
                    final_status = "approved"
                elif config.auto_withdraw_limit <= amount <= config.admin_review_limit:
                    if is_kyc_approved and is_2fa_enabled:
                        final_status = "approved"
                    else:
                        final_status = "pending"
                        admin_note_text = f"Security Alert: Auto-approval denied."
                else:
                    final_status = "pending"
                    admin_note_text = f"Security Alert: High-value transaction."

            # 🛡️ کسر مبلغ کل از ولت
            if final_status == "approved":
                unique_tx_code = f"TXN-{uuid.uuid4().hex[:8].upper()}"
                wallet.balance -= total_deduction
                wallet.save()

                # 🌟 واریز فوری کارمزد به خزانه
                revenue_acc = PlatformRevenue.get_revenue_account(selected_currency)  # 👈 کد ارز را می‌فرستیم
                revenue_acc.balance += fee
                revenue_acc.save()
                RevenueJournal.objects.create(
                    account=revenue_acc, amount=fee,
                    balance_before=revenue_acc.balance - fee,
                    balance_after=revenue_acc.balance,
                    user_email=request.user.email
                )

                withdraw_status, tx_status, tx_hash_val = 'done', 'success', unique_tx_code
                time_of_processing = timezone.now()
            else:
                wallet.balance -= total_deduction
                wallet.frozen_balance += total_deduction
                wallet.save()
                withdraw_status, tx_status, tx_hash_val = 'pending', 'pending', None
                time_of_processing = None

            # ذخیره درخواست
            withdraw = WithdrawRequest.objects.create(
                wallet=wallet, user=request.user, amount=amount,
                fee=fee, target_address=address,
                status=withdraw_status, tx_hash=tx_hash_val, admin_note=admin_note_text,
                processed_by=None, processed_at=time_of_processing
            )

            unique_id = uuid.uuid4()
            WalletTransaction.objects.create(
                wallet=wallet, withdraw=withdraw, tx_hash=f"WD-{withdraw.id}-{unique_id.hex[:8]}",
                amount=amount, type="withdraw", status=tx_status, payment_id=f"WD-PAY-{unique_id}",
                purchase_id=f"WD-PUR-{unique_id}", pay_address=address,
                expires_at=timezone.now() + timedelta(minutes=60),
            )

        # پیام موفقیت
        if final_status == "approved":
            messages.success(request, f"Withdrawal processed. Fee: {fee} {wallet.currency_upper} applied.",
                             extra_tags="withdraw")
        else:
            messages.success(request, f"Request submitted. Fee: {fee} {wallet.currency_upper} will be applied.",
                             extra_tags="withdraw")

        return redirect(f"/my-wallet/?currency={selected_currency}")


class CreateDepositView(LoginRequiredMixin, View):
    template_name = "wallet/buy-and-sell.html"

    def get(self, request):
        selected_currency = request.GET.get('currency', 'usdttrc20').lower()

        # 🛡️ تضمین عدم بروز خطای DoesNotExist با لایه زاپاس
        wallet = get_or_create_wallet_safely(request.user, selected_currency)
        now = timezone.now()

        # بررسی تراکنش پندینگ اختصاصی این ارز
        pending_tx = WalletTransaction.objects.filter(
            wallet=wallet, status="pending", type="deposit", expires_at__gt=now
        ).first()

        context = {'wallet': wallet, 'selected_currency': selected_currency}
        if pending_tx:
            context.update({
                "pending_wallet_address": pending_tx.pay_address,
                "pending_amount": pending_tx.amount,
                "pending_payment_id": pending_tx.payment_id,
                "pending_expires_at": int(pending_tx.expires_at.timestamp()),
            })

        if request.GET.get("check_pending") == "1":
            return JsonResponse({
                "wallet_address": context.get("pending_wallet_address"),
                "amount": str(context.get("pending_amount")) if context.get("pending_amount") else None,
                "payment_id": context.get("pending_payment_id"),
                "expires_at": context.get("pending_expires_at"),
            })

        return render(request, self.template_name, context)

    def post(self, request):
        amount_raw = request.POST.get("amount")
        selected_currency = request.POST.get("currency", "usdttrc20").lower()

        try:
            amount = Decimal(amount_raw)
        except Exception:
            return JsonResponse({"error": "Invalid amount format"}, status=400)

        if amount <= 0:
            return JsonResponse({"error": "Amount must be greater than zero"}, status=400)

        # 🛡️ لایه محافظتی در متد POST
        wallet = get_or_create_wallet_safely(request.user, selected_currency)

        pending_tx = WalletTransaction.objects.filter(
            wallet=wallet, type="deposit", status="pending"
        ).first()

        if pending_tx:
            if pending_tx.expires_at <= timezone.now():
                pending_tx.status = "failed"
                pending_tx.save()
            else:
                return JsonResponse({
                    "wallet_address": pending_tx.pay_address,
                    "amount": str(pending_tx.amount),
                    "status": pending_tx.status,
                    "payment_id": pending_tx.payment_id,
                    "expires_at": int(pending_tx.expires_at.timestamp()),
                    "msg": "Existing pending deposit returned."
                })

        # --- فراخوانی داینامیک API بر اساس ارز انتخابی کاربر ---
        url = "https://api.nowpayments.io/v1/payment"
        headers = {
            "x-api-key": settings.NOW_PAYMENT_API_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "price_amount": float(amount),
            "price_currency": "usd",
            "pay_currency": selected_currency,
            "ipn_callback_url": request.build_absolute_uri("/wallet/nowpayments/callback/"),
            "order_id": f"DEP-{wallet.user.id}-{uuid.uuid4().hex[:8]}",
            "order_description": f"Deposit ${amount} {selected_currency.upper()} to wallet",
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            data = response.json()
            if response.status_code not in [200, 201]:
                return JsonResponse({"error": data.get("message", "NowPayments API Error")}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"Connection failed: {str(e)}"}, status=500)

        pay_address = data.get("pay_address")
        pay_amount = data.get("pay_amount")
        payment_id = data.get("payment_id")
        p_id = data.get("purchase_id") or f"PUR-{uuid.uuid4().hex[:10]}"

        if payment_id and pay_address:
            tx = WalletTransaction.objects.create(
                wallet=wallet, tx_hash=payment_id, amount=amount, type="deposit",
                confirmed=False, status="pending", purchase_id=p_id,
                payment_id=payment_id, pay_address=pay_address,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            return JsonResponse({
                "wallet_address": pay_address,
                "amount": str(pay_amount),
                "status": "pending",
                "expires_at": int(tx.expires_at.timestamp()),
                "payment_id": tx.payment_id,
            })

        return JsonResponse({"error": "Failed to generate payment address from provider"}, status=500)

    def patch(self, request):
        selected_currency = request.GET.get('currency', 'usdttrc20').lower()

        # 🛡️ لایه محافظتی در متد PATCH
        wallet = get_or_create_wallet_safely(request.user, selected_currency)

        pending_tx = WalletTransaction.objects.filter(
            wallet=wallet,
            type="deposit",
            status="pending"
        ).first()

        if pending_tx:
            pending_tx.status = "failed"
            pending_tx.save()
            return JsonResponse({"status": "cancelled"})

        return JsonResponse({"error": "No pending transaction found to cancel."}, status=404)


class GetPaymentStatusView(View):
    def get(self, request):
        payment_id = request.GET.get("payment_id")
        if not payment_id:
            return JsonResponse({"error": "payment_id is required"}, status=400)

        try:
            transaction = WalletTransaction.objects.get(payment_id=payment_id)
            return JsonResponse({
                "status": transaction.status,
                "amount": str(transaction.amount),
                "user_message": transaction.user_message or "⏳ Waiting for payment...",
            })
        except WalletTransaction.DoesNotExist:
            return JsonResponse({"error": "transaction not found"}, status=404)


@method_decorator(csrf_exempt, name="dispatch")
class NowPaymentsCallbackView(View):
    def post(self, request):
        # ۱. دریافت امضا از هدر
        received_sig = request.headers.get("x-nowpayments-sig")
        if not received_sig:
            return JsonResponse({"error": "No signature provided"}, status=400)

        # ۲. استفاده مستقیم از بایت‌های خامِ بدنه بدون دستکاری یا مرتب‌سازی دستی
        raw_payload = request.body

        try:
            # ۳. محاسبه امضای محلی بر اساس دیتای خام ورودی
            local_sig = hmac.new(
                settings.NOW_PAYMENT_IPN_KEY.encode('utf-8'),
                raw_payload,
                hashlib.sha512
            ).hexdigest()

            # ۴. مقایسه امن در زمان ثابت (Constant Time)
            # 🔍 موقتاً برای پیدا کردن مغایرت اضافه کنید:
            print(f"📥 Received Sig: {received_sig}")
            print(f"💻 Computed Sig: {local_sig}")
            print(f"📦 Raw Payload: {raw_payload}")
            if not hmac.compare_digest(local_sig, received_sig):
                logger.warning(f"Security Breach Attempt: Invalid Signature detected.")
                return JsonResponse({"error": "Security Breach: Invalid Signature"}, status=403)

            # ۵. حالا با خیال راحت دیتا را برای پردازش دیتابیس پارس می‌کنیم
            data = json.loads(raw_payload.decode("utf-8"))
            payment_id = data.get("payment_id")
            status = data.get("payment_status")

            with transaction.atomic():
                # استفاده از select_for_update برای قفل کردن ردیف در سطح دیتابیس
                tx = WalletTransaction.objects.select_related("wallet").select_for_update().filter(
                    payment_id=payment_id).first()
                if not tx:
                    return JsonResponse({"error": "Transaction not found"}, status=404)

                if tx.status == "success":
                    return JsonResponse({"status": "already processed"})

                if status in ["finished", "confirmed"]:
                    tx.status = "success"
                    tx.confirmed = True
                    tx.user_message = "✅ Deposit confirmed successfully."

                    wallet = tx.wallet
                    wallet.balance += tx.amount
                    wallet.save()

                elif status in ["failed", "expired"]:
                    tx.status = "failed"
                    tx.user_message = "❌ Transaction expired or failed."

                tx.save()

            return JsonResponse({"status": "ok"})

        except Exception as e:
            logger.error(f"IPN Processing Error: {str(e)}")
            return JsonResponse({"error": "Internal server error"}, status=500)


class LatestTransaction(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Unauthorized"}, status=401)

        # 🛡️ بررسی وجود کیف‌پول از روی ریلیشن جدید دیتابیس
        if not request.user.crypto_wallets.exists():
            return JsonResponse({
                "main_transaction": [],
                "last_six_transactions": [],
                "error": "No wallet found for this account"
            })

        now = timezone.now()
        # فیلتر و شکست دادن تراکنش‌های پندینگ منقضی شده برای تمام ارزهای این کاربر
        WalletTransaction.objects.filter(
            wallet__user=request.user,
            type="deposit",
            status="pending",
            expires_at__lte=now
        ).update(status="failed")

        # واکشی کل تراکنش‌های مالتی‌کارنسی کاربر
        transactions_qs = WalletTransaction.objects.filter(
            wallet__user=request.user
        ).select_related('wallet', 'withdraw').order_by("-timestamp")

        last_six_transactions = transactions_qs[:6]

        def serialize(tx_list):
            return [
                {
                    "id": tx.id,
                    "timestamp": tx.timestamp.strftime("%H:%M - %Y/%m/%d"),
                    "tx_hash": tx.tx_hash or "---",
                    "type": tx.type,
                    "amount": float(tx.amount),
                    "status": tx.status,
                    "processed_at_date": tx.withdraw.processed_at.strftime("%b %d")
                    if (getattr(tx, 'withdraw', None) and tx.withdraw.processed_at) else None,
                    "processed_at_time": tx.withdraw.processed_at.strftime("%H:%M")
                    if (getattr(tx, 'withdraw', None) and tx.withdraw.processed_at) else None,
                }
                for tx in tx_list
            ]

        page_number = request.GET.get("page", 1)
        per_page = 15
        paginator = Paginator(transactions_qs, per_page)
        page_obj = paginator.get_page(page_number)

        return JsonResponse({
            "main_transaction": serialize(page_obj.object_list),
            "last_six_transactions": serialize(last_six_transactions),
            "per_page": paginator.per_page,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        })


class RecentActivityView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            # ۱. دریافت پارامتر فیلتر متنی از فرانت‌اِند
            filter_type = request.GET.get('filter', 'today')
            today = timezone.now().date()

            # ۲. نگاشت دقیق بازه‌های زمانی
            if filter_type == 'today':
                end_date = today
                start_date = today - timedelta(days=2)
            elif filter_type == '3days':
                end_date = today - timedelta(days=3)
                start_date = today - timedelta(days=5)
            elif filter_type == 'older':
                end_date = today - timedelta(days=6)
                start_date = today - timedelta(days=8)
            else:
                end_date = today
                start_date = today - timedelta(days=2)

            # ۳. اجرای کوئری‌ها همراه با متد .order_by() جهت شکستن تله حذف گروه‌بندی دیتابیس
            trades = Prediction.objects.filter(
                user=request.user,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            ).annotate(d=TruncDate('created_at')).values('d').annotate(
                count=Count('id')).order_by()  # ⚡ پاکسازی اوردرینگ پیش‌فرض

            txs = WalletTransaction.objects.filter(
                wallet__user=request.user,
                timestamp__date__gte=start_date,
                timestamp__date__lte=end_date
            ).annotate(d=TruncDate('timestamp')).values('d', 'type').annotate(count=Count('id')).order_by()

            tickets = UserTicket.objects.filter(
                user=request.user,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            ).annotate(d=TruncDate('created_at')).values('d').annotate(count=Count('id')).order_by()

            # ۴. تجمیع دیتای نهایی در دیکشنری هماهنگ با فرانت‌اِند
            summary = {}

            for item in trades:
                d = item['d'].strftime('%Y-%m-%d')
                if d not in summary:
                    summary[d] = {'date': d, 'trades': 0, 'deposit': 0, 'withdraw': 0, 'tickets': 0}
                summary[d]['trades'] = item['count']

            for item in txs:
                d = item['d'].strftime('%Y-%m-%d')
                if d not in summary:
                    summary[d] = {'date': d, 'trades': 0, 'deposit': 0, 'withdraw': 0, 'tickets': 0}

                # تطابق کامل با چویزهای مدل (deposit / withdraw)
                tx_type = item['type'].lower() if item['type'] else ''
                if tx_type in ['deposit', 'withdraw']:
                    summary[d][tx_type] = item['count']

            for item in tickets:
                d = item['d'].strftime('%Y-%m-%d')
                if d not in summary:
                    summary[d] = {'date': d, 'trades': 0, 'deposit': 0, 'withdraw': 0, 'tickets': 0}
                summary[d]['tickets'] = item['count']

            # مرتب‌سازی نزولی بر اساس تاریخ روزها
            result = sorted(summary.values(), key=lambda x: x['date'], reverse=True)

            return JsonResponse({
                "status": "success",
                "activities": result,
                "has_next": False
            })

        except Exception as e:
            # در صورت بروز هرگونه خطای سروری، جزئیات کاملاً به فرانت‌اِند پاس داده می‌شود تا سیستم قفل نشود
            error_trace = traceback.format_exc()
            return JsonResponse({
                "status": "error",
                "message": str(e),
                "trace": error_trace
            }, status=500)


class WithdrawTransactionList(LoginRequiredMixin, View):
    login_url = "/sign_in/"
    template_name = "transaction/withdraw-transaction.html"

    def get(self, request):
        # ۱. دریافت کوئری پایه و بهینه‌سازی با select_related برای کاهش Queryها به دیتابیس
        transactions_qs = WalletTransaction.objects.filter(
            wallet__user=request.user,
            type="withdraw"
        ).select_related("wallet", "wallet__user", "withdraw").order_by("-timestamp")

        # ۲. فیلتر جستجوی متنی (فیلد ناموجود withdraw_tx_hash کاملاً حذف شد)
        query = request.GET.get('q', '').strip()
        if query:
            transactions_qs = transactions_qs.filter(
                Q(tx_hash__icontains=query) |
                Q(pay_address__icontains=query) |
                Q(withdraw__target_address__icontains=query) |
                Q(withdraw__tx_hash__icontains=query) |
                Q(amount__icontains=query)
            )


        currency_filter = request.GET.get('currency', '').strip().lower()
        if currency_filter and currency_filter != 'all':
            transactions_qs = transactions_qs.filter(wallet__currency=currency_filter)


        date_range = request.GET.get('date_range', '').strip()
        now = timezone.now()
        if date_range == 'today':
            transactions_qs = transactions_qs.filter(timestamp__date=now.date())
        elif date_range == '7_days':
            transactions_qs = transactions_qs.filter(timestamp__gte=now - datetime.timedelta(days=7))
        elif date_range == '30_days':
            transactions_qs = transactions_qs.filter(timestamp__gte=now - datetime.timedelta(days=30))

        paginator = Paginator(transactions_qs, 10)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        # ۵. سریالایزر بهینه و کاملاً ایمن بدون ریسک کرش یا خطای AttributeError
        def serialize(tx_list):
            result = []
            for tx in tx_list:

                if tx.withdraw:
                    admin_tx_hash = tx.withdraw.tx_hash or "-"
                    target_address = tx.withdraw.target_address or tx.pay_address or "-"
                else:
                    admin_tx_hash = "-"
                    target_address = tx.pay_address or "-"

                result.append({
                    "id": tx.id,
                    "timestamp": tx.timestamp.strftime("%d %b, %Y %H:%M"),
                    "tx_hash": tx.tx_hash or "-",
                    "admin_tx_hash": admin_tx_hash,
                    "target_address": target_address,
                    "user_email": tx.wallet.user.email,
                    "type": tx.type,
                    "amount": float(tx.amount),
                    "currency": tx.wallet.currency.upper(),
                    "status": tx.status,
                })
            return result

        # پاسخ به درخواست‌های AJAX فرانت‌آند
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "main_transaction": serialize(page_obj.object_list),
                "per_page": paginator.per_page,
                "num_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "total_entries": paginator.count,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            })


        return render(request, self.template_name, {"transactions": page_obj})


class DepositTransactionList(LoginRequiredMixin, View):
    login_url = "/sign_in/"
    template_name = "transaction/deposit-transaction.html"

    def get(self, request):
        # کوئری پایه تراکنش‌ها
        transactions_qs = (
            WalletTransaction.objects.filter(
                wallet__user=request.user, type="deposit"
            )
            .select_related("wallet", "wallet__user")
            .order_by("-timestamp")
        )

        # ۱. دریافت دقیق پارامترها از فرانت‌آند
        query = request.GET.get("q", "").strip()
        date_filter = request.GET.get("date_filter", "all").strip()

        # ۲. اعمال فیلتر هوشمند بازه زمانی
        now = timezone.now()
        if date_filter == "today":
            transactions_qs = transactions_qs.filter(timestamp__date=now.date())
        elif date_filter == "7_days":
            transactions_qs = transactions_qs.filter(
                timestamp__gte=now - timedelta(days=7)
            )
        elif date_filter == "30_days":
            transactions_qs = transactions_qs.filter(
                timestamp__gte=now - timedelta(days=30)
            )

        # 🛠️ ۳. فیلتر متنی قطعی (تضمین حذف ردیف‌های غیرمرتبط در دیتابیس)
        if query:
            transactions_qs = transactions_qs.filter(
                Q(tx_hash__icontains=query)
                | Q(wallet__user__email__icontains=query)
                | Q(wallet__currency__icontains=query)
                | Q(status__icontains=query)  # <-- فیلتر مستقیم روی وضعیت (Success / Failed)
            )

        # ۴. پجینیشن روی دیتای فیلتر شده نهایی
        paginator = Paginator(transactions_qs, 20)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        def serialize(tx_list):
            return [
                {
                    "id": tx.id,
                    "timestamp": tx.timestamp.strftime("%d %b, %Y %H:%M"),
                    "tx_hash": tx.tx_hash,
                    "user_email": tx.wallet.user.email,
                    "type": tx.type,
                    "currency": tx.wallet.currency_upper,
                    "currency_raw": tx.wallet.currency.lower(),
                    "amount": float(tx.amount),
                    "status": tx.status,
                }
                for tx in tx_list
            ]

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "main_transaction": serialize(page_obj.object_list),
                    "per_page": paginator.per_page,
                    "num_pages": paginator.num_pages,
                    "current_page": page_obj.number,
                    "total_entries": paginator.count,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                }
            )

        return render(request, self.template_name, {"transactions": page_obj})


class UserWalletStatsAPI(LoginRequiredMixin, KYCRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # 🎯 گرفتن ارز انتخاب شده از ریکوئست (پیش‌فرض تتر)
        currency_ticker = request.GET.get('currency', 'usdttrc20').strip().lower()

        # پیدا کردن ولت اختصاصی همان ارز برای کاربر
        wallet = DollarWallet.objects.filter(user=request.user, currency=currency_ticker).first()

        if not wallet:
            return JsonResponse({
                "total_deposits": "0.00", "total_withdraws": "0.00",
                "net_flow": "0.00", "wallet_volume": "0.00", "ticker": currency_ticker.upper()
            })

        # فیلتر دقیق تراکنش‌های همان کیف پول
        total_dep = WalletTransaction.objects.filter(
            wallet=wallet, type='deposit', status__iexact='success'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        total_wit = WithdrawRequest.objects.filter(
            wallet=wallet, status__iexact='done'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        return JsonResponse({
            "total_deposits": f"{total_dep:.2f}" if currency_ticker not in ['btc', 'eth'] else f"{total_dep:.6f}",
            "total_withdraws": f"{total_wit:.2f}" if currency_ticker not in ['btc', 'eth'] else f"{total_wit:.6f}",
            "net_flow": f"{(total_dep - total_wit):.2f}" if currency_ticker not in ['btc',
                                                                                    'eth'] else f"{(total_dep - total_wit):.6f}",
            "wallet_volume": f"{(total_dep + total_wit):.2f}" if currency_ticker not in ['btc',
                                                                                         'eth'] else f"{(total_dep + total_wit):.6f}",
            "ticker": currency_ticker.upper()  # ارسال تیکر جهت نمایش داینامیک واحد پول
        })


class UserWalletCashFlowAPI(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        user = request.user
        currency_ticker = request.GET.get('currency', 'usdttrc20').strip().lower()

        # پیدا کردن ولت اختصاصی ارز برای کاربر
        wallet = DollarWallet.objects.filter(user=user, currency=currency_ticker).first()

        # بازه زمانی ۷ روز گذشته
        today = timezone.now().date()
        start_date = today - timedelta(days=6)
        date_list = [start_date + timedelta(days=i) for i in range(7)]

        categories = [date.strftime('%b %d') for date in date_list]

        # مقداردهی اولیه نمودار با صفر
        deposits_map = {date: 0.0 for date in date_list}
        withdraws_map = {date: 0.0 for date in date_list}

        if wallet:
            # 📊 ۱. اصلاح فیلد زمان به timestamp برای تراکنش‌های WalletTransaction (واریزها)
            dep_query = WalletTransaction.objects.filter(
                wallet=wallet,
                type='deposit',
                status__iexact='success',
                timestamp__date__gte=start_date  # 🛠️ تغییر از created_at به timestamp
            ).annotate(day=TruncDay('timestamp')).values('day').annotate(total=Sum('amount'))  # 🛠️ تغییر به timestamp

            for item in dep_query:
                item_date = item['day'].date()
                if item_date in deposits_map:
                    deposits_map[item_date] = float(item['total'] or 0)

            # 📊 ۲. استفاده از created_at برای WithdrawRequest (برداشت‌ها کاملاً درست است)
            wit_query = WithdrawRequest.objects.filter(
                wallet=wallet,
                status__iexact='done',
                created_at__date__gte=start_date  # این مدل فیلد created_at را دارد و درست است
            ).annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('amount'))

            for item in wit_query:
                item_date = item['day'].date()
                if item_date in withdraws_map:
                    withdraws_map[item_date] = float(item['total'] or 0)

        return JsonResponse({
            "categories": categories,
            "deposits": [deposits_map[date] for date in date_list],
            "withdraws": [withdraws_map[date] for date in date_list],
            "ticker": currency_ticker.upper()
        })
