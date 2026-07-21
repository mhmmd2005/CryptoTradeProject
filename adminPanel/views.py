import base64
import csv
import json
import logging
import random
from datetime import date
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
from functools import wraps
from io import BytesIO

import pyotp
import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, DecimalField, IntegerField
from django.db.models import Q
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from Prediction.models import PredictionRound, Prediction
from Prediction.utils import get_live_price
from UserPanel.models import UserTicket
from accounts.models import User
from adminPanel.forms import AdminLoginForm, AdminLockScreen, AdminRegistrationForm, AdminPasswordChangeForm
from adminPanel.models import TicketReply, PlatformRevenue, RevenueJournal, AdminWithdrawal, AdminUser, \
    AdminLog, AdminInvitation
from adminPanel.tasks import send_admin_invitation_email, send_admin_edit_otp_task, send_delete_otp_task, \
    send_admin_activation_email
from adminPanel.utils import check_admin_lock, register_failed_attempt, reset_failed_attempts, log_admin_activity, \
    get_platform_liquidity_data
from dashboard.models import UserProfile, ProfileApprovalStatus, Notification, UserBanHistory, InternalTrade
from wallet.models import WithdrawRequest, WalletTransaction, DollarWallet
from .forms import AdminPredictionRoundForm

logger = logging.getLogger(__name__)


# ---------------- Admin Login ----------------

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ---------------- Admin Login ----------------
@method_decorator(never_cache, name='dispatch')
class AdminLoginView(View):
    template_name = 'adminpanel/adminPanel/admin_login.html'

    def _get_or_create_admin_session(self, request):
        admin_key = request.COOKIES.get("admin_sessionid")
        if admin_key:
            try:
                return SessionStore(session_key=admin_key), None
            except:
                pass
        admin_session = SessionStore()
        admin_session.create()
        return admin_session, admin_session.session_key

    def get(self, request):
        admin_session, new_key = self._get_or_create_admin_session(request)
        locked_until_ts = check_admin_lock(request)

        context = {
            'form': AdminLoginForm(),
            'is_locked': False,
        }

        if locked_until_ts:
            now_ts = int(timezone.now().timestamp())
            context['is_locked'] = True
            context['lock_seconds'] = max(0, locked_until_ts - now_ts)

        response = render(request, self.template_name, context)
        if new_key:
            response.set_cookie("admin_sessionid", new_key, httponly=True, secure=False, samesite='Lax')
        return response

    def post(self, request):
        admin_session, new_key = self._get_or_create_admin_session(request)
        email = request.POST.get("email", "").lower().strip()

        # ۱. بررسی قفل بودن پورتال بر اساس IP کلاینت و ایمیل هدف
        locked_until_ts = check_admin_lock(request, email=email)
        if locked_until_ts:
            now_ts = int(timezone.now().timestamp())
            return render(request, self.template_name, {
                'form': AdminLoginForm(request.POST),
                'is_locked': True,
                'lock_seconds': max(0, locked_until_ts - now_ts),
            })

        otp_code = request.POST.get("otp_code")

        # ۲. تایید هویت مرحله دوم (ورود کد OTP)
        if otp_code:
            password = request.POST.get("password")

            user = authenticate(
                request,
                username=email,
                password=password,
                backend='adminPanel.backends.AdminUserBackend'
            )

            if user and isinstance(user, AdminUser) and user.is_active and user.is_otp_enabled:
                totp = pyotp.totp.TOTP(user.otp_secret)

                if totp.verify(otp_code.replace(' ', '').strip(), valid_window=1):
                    return self._login_admin_success(request, user, admin_session)

            # ثبت خطا و بررسی آنی قفل جهت مسدودسازی بدون وقفه
            register_failed_attempt(request, email=email)

            locked_until_ts = check_admin_lock(request, email=email)
            if locked_until_ts:
                now_ts = int(timezone.now().timestamp())
                return render(request, self.template_name, {
                    'form': AdminLoginForm(request.POST),
                    'is_locked': True,
                    'lock_seconds': max(0, locked_until_ts - now_ts),
                })

            form = AdminLoginForm(request.POST)
            form.is_valid()
            form.add_error(None, "Invalid verification code.")

            return render(request, self.template_name, {
                'form': form,
                'is_locked': False,
                'show_otp': True
            })

        # ۳. تایید هویت مرحله اول (ایمیل و رمزعبور)
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            email_cleaned = form.cleaned_data["email"].lower().strip()
            password = form.cleaned_data["password"]

            user = authenticate(
                request,
                username=email_cleaned,
                password=password,
                backend='adminPanel.backends.AdminUserBackend'
            )

            if not user or not isinstance(user, AdminUser) or not user.is_active:
                register_failed_attempt(request, email=email_cleaned)

                locked_until_ts = check_admin_lock(request, email=email_cleaned)
                if locked_until_ts:
                    now_ts = int(timezone.now().timestamp())
                    return render(request, self.template_name, {
                        'form': form,
                        'is_locked': True,
                        'lock_seconds': max(0, locked_until_ts - now_ts),
                    })

                form.add_error(None, "Access Denied: Invalid email or password")
                return render(request, self.template_name, {'form': form})

            # ریدایرکت ادمین به بخش دریافت OTP در صورت فعال بودن
            if user.is_otp_enabled:
                return render(request, self.template_name, {
                    'form': form,
                    'is_locked': False,
                    'show_otp': True
                })

            return self._login_admin_success(request, user, admin_session)

        register_failed_attempt(request, email=email)
        return render(request, self.template_name, {'form': form})

    def _login_admin_success(self, request, user, admin_session):
        """متد نهایی‌سازی تراکنش اتمیک ورود موفقیت‌آمیز ادمین"""
        reset_failed_attempts(request, email=user.email)

        messages.success(request, "Authentication successful. Welcome back.")

        try:
            with transaction.atomic():
                user.last_login = timezone.now()
                user.last_login_ip = get_client_ip(request)
                user.save(update_fields=['last_login', 'last_login_ip'])

                log_admin_activity(request, 'LOGIN', description="Successfully logged in to the panel")
        except Exception as e:
            messages.error(request, "Database transaction error. Access denied for compliance.")
            return redirect("admin-login")

        admin_session["admin_user_id"] = user.id
        admin_session.save()

        response = redirect("admin-panel")
        response.set_cookie(
            "admin_sessionid",
            admin_session.session_key,
            httponly=True,
            secure=False,
            samesite='Lax'
        )
        return response


# ---------------- Admin Required Mixin ----------------

class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        admin_key = request.COOKIES.get("admin_sessionid")

        # ۱. چک کردن سریع بدون درگیری با دیتابیس (Early Exit)
        if not admin_key:
            return redirect("admin-login")

        # ۲. استفاده از Cache برای جلوگیری از فشار به دیتابیس در هر کلیک
        # ما اطلاعات ادمین را برای ۳۰ دقیقه در رم نگه می‌داریم
        cache_key = f"admin_auth_{admin_key}"
        admin_data = cache.get(cache_key)

        if not admin_data:
            session = SessionStore(session_key=admin_key)
            admin_user_id = session.get("admin_user_id")

            if not admin_user_id:
                return redirect("admin-login")

            try:
                admin_user = AdminUser.objects.get(id=admin_user_id, is_active=True)
                # ذخیره در کش برای بهبود سرعت (حتی برای ۱ دقیقه هم عالی است)
                cache.set(cache_key, admin_user, 60 * 5)
            except AdminUser.DoesNotExist:
                response = redirect("admin-login")
                response.delete_cookie("admin_sessionid")
                return response
        else:
            admin_user = admin_data

        # ۳. تزریق هوشمند به ریکوئست
        request.admin_user = admin_user
        request.admin_user_id = admin_user.id
        request.is_admin_panel = True

        return super().dispatch(request, *args, **kwargs)


# 5. میکس‌این برای ادمین‌های ارشد
class SeniorAdminRequiredMixin(AdminRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(response, 'status_code') and response.status_code in [301, 302]:
            return response

        if not request.admin_user or not request.admin_user.is_senior:
            messages.error(request,
                           "Unauthorized Access. Senior-level permissions are required to access this section.")
            return redirect('admin-list')
        return response


def admin_permission_required(permission_name):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(arg1, *args, **kwargs):
            # هوشمندی در تشخیص نوع ورودی (CBV vs FBV)
            request = arg1.request if hasattr(arg1, 'request') else arg1

            # استفاده از ویژگی hasattr برای امنیت بیشتر
            admin_user = getattr(request, 'admin_user', None)

            # اگر به هر دلیلی میکس‌این اجرا نشده بود، امنیت را فدا نکن
            if not admin_user:
                # 🛡️ لایه محافظتی ثانویه: تلاش برای بازیابی مستقیم
                admin_key = request.COOKIES.get("admin_sessionid")
                if admin_key:
                    # سعی کن از کش بگیری (همان منطق میکس‌این)
                    admin_user = cache.get(f"admin_auth_{admin_key}")
                    if admin_user:
                        request.admin_user = admin_user
                    else:
                        # اگر در کش نبود، از سشن و دیتابیس (فقط برای اطمینان)
                        session = SessionStore(session_key=admin_key)
                        uid = session.get("admin_user_id")
                        if uid:
                            admin_user = AdminUser.objects.filter(id=uid, is_active=True).first()
                            if admin_user:
                                request.admin_user = admin_user
                                cache.set(f"admin_auth_{admin_key}", admin_user, 300)

                # حالا اگر باز هم نبود، ریدایرکت کن
            if not admin_user:
                return redirect("admin-login")

            # ۴. هوشمندی در چک کردن پرمیشن‌ها (پشتیبانی از لیست یا تک پرمیشن)
            user_perms = admin_user.permissions or []

            # سوپر ادمین یا داشتن پرمیشن خاص
            has_perm = admin_user.is_senior or permission_name in user_perms

            if has_perm:
                return view_func(arg1, *args, **kwargs)

            # ۵. به جای ارور ۴۰۳ زشت، پیام مودبانه بدیم
            messages.error(request,
                           f"Access Denied: You do not have the required privileges for the [{permission_name}] section.")
            return redirect("admin-panel")  # یا هر جایی که صلاح می‌دانید

        return _wrapped_view

    return decorator


class PlatformRevenueAPIView(SeniorAdminRequiredMixin, View):

    def get(self, request):
        # دریافت موجودی تمام ارزها به صورت یکجا
        all_revenues = PlatformRevenue.objects.all()
        # تبدیل به یک دیکشنری برای نمایش در دشبورد
        data = {rev.currency: float(rev.balance) for rev in all_revenues}

        return JsonResponse({
            "status": "success",
            "balances": data
        })

    def post(self, request):
        try:
            raw_amount = request.POST.get('amount', '0')
            address = request.POST.get('address', '').strip()
            currency = request.POST.get('currency', 'usdttrc20').lower()

            # محاسبه و تمیزکاری مبلغ (فقط یک بار انجام می‌شود)
            try:
                amount = Decimal(raw_amount.replace(',', ''))
            except (InvalidOperation, ValueError):
                return JsonResponse({"status": "error", "message": "Invalid amount format."})

            if amount <= 0:
                return JsonResponse({"status": "error", "message": "Amount must be greater than zero."})

            if not address:
                return JsonResponse({"status": "error", "message": "Destination wallet address is required."})

            # دریافت حساب خزانه مربوط به ارز انتخاب شده
            revenue_acc = PlatformRevenue.get_revenue_account(currency)

            if revenue_acc.balance < amount:
                return JsonResponse({"status": "error", "message": f"Insufficient balance in {currency.upper()}."})

            # ایجاد درخواست برداشت ادمین
            # در بخش post مربوط به کلاس PlatformRevenueAPIView
            AdminWithdrawal.objects.create(
                admin=request.admin_user,
                amount=amount,
                currency=currency,  # 👈 اضافه کردن این فیلد
                destination_wallet=address,
                status='pending',
                description="Manual senior admin withdrawal request"
            )

            return JsonResponse({
                "status": "success",
                "message": f"Withdrawal request for {amount:,.2f} {currency.upper()} submitted for approval."
            })

        except Exception as e:
            logger.error(f"Error in PlatformRevenueAPIView: {e}")
            return JsonResponse({"status": "error", "message": "A system error occurred."})


class PlatformWithdrawalActionView(SeniorAdminRequiredMixin, View):
    # مقدار pk=None باعث می‌شود هم با آیدی و هم بدون آیدی کار کند
    def get(self, request, pk=None):
        withdrawals = AdminWithdrawal.objects.all()[:20]
        return render(request, 'adminpanel/partial/withdrawal_table_rows.html', {
            'withdrawals': withdrawals
        })

    def post(self, request, pk):
        action = request.POST.get('action')

        with transaction.atomic():
            # ۱. قفل کردن ردیف با select_for_update برای جلوگیری از Race Condition
            withdrawal = get_object_or_404(AdminWithdrawal.objects.select_for_update(), id=pk)

            # ۲. چک کردن وضعیت: اگر وضعیت از pending خارج شده، یعنی قبلاً پردازش شده
            if withdrawal.status != 'pending':
                # بازگرداندن لیست بدون هیچ عملیات مالی اضافه
                withdrawals = AdminWithdrawal.objects.all().order_by('-created_at')[:20]
                return render(request, 'adminpanel/partial/withdrawal_table_rows.html', {'withdrawals': withdrawals})

            if action == 'approve':
                revenue_acc = PlatformRevenue.get_revenue_account(withdrawal.currency)
                revenue = PlatformRevenue.objects.select_for_update().get(id=revenue_acc.id)

                if revenue_acc.balance >= withdrawal.amount:
                    old_bal = revenue.balance
                    revenue.balance -= withdrawal.amount
                    revenue.save(update_fields=["balance"])

                    RevenueJournal.objects.create(
                        account=revenue,
                        amount=-withdrawal.amount,
                        balance_before=old_bal,
                        balance_after=revenue.balance,
                        user_email=f"Approved by {request.admin_user.email}"
                    )
                    withdrawal.status = 'approved'
                else:
                    return HttpResponse("Insufficient Balance", status=400)
            else:
                withdrawal.status = 'rejected'

            withdrawal.approved_by = request.admin_user
            withdrawal.save()  # وضعیت اینجا تغییر می‌کند و در درخواست دوم شرط pending با شکست مواجه می‌شود

        withdrawals = AdminWithdrawal.objects.all()[:20]
        return render(request, 'adminpanel/partial/withdrawal_table_rows.html', {'withdrawals': withdrawals})


class AdminListView(AdminRequiredMixin, View):
    template_name = 'adminpanel/adminPanel/admin_list.html'

    def get(self, request):
        search_query = request.GET.get('q', '')
        status_filter = request.GET.get('filter', 'all')

        f_day = request.GET.get('fDay')
        f_month = request.GET.get('fMonth')
        f_year = request.GET.get('fYear')
        t_day = request.GET.get('tDay')
        t_month = request.GET.get('tMonth')
        t_year = request.GET.get('tYear')

        admins = AdminUser.objects.all().order_by('-id')

        if status_filter == 'active':
            admins = admins.filter(is_active=True)
        elif status_filter == 'inactive':
            admins = admins.filter(is_active=False)
        elif status_filter == 'senior':
            admins = admins.filter(is_senior=True)

        try:
            if f_day and f_month and f_year:
                admins = admins.filter(date_joined__date__gte=date(int(f_year), int(f_month), int(f_day)))
            if t_day and t_month and t_year:
                admins = admins.filter(date_joined__date__lte=date(int(t_year), int(t_month), int(t_day)))
        except (ValueError, TypeError):
            pass

        if search_query:
            admins = admins.filter(
                Q(email__icontains=search_query) |
                Q(full_name__icontains=search_query)
            )

        senior_count = AdminUser.objects.filter(is_senior=True).count()

        context = {
            'admins': admins,
            'current_admin': request.admin_user,
            'senior_count': senior_count,
            'search_query': search_query,
            'current_filter': status_filter,
            'f_date': {'d': f_day, 'm': f_month, 'y': f_year},  # برای نگه داشتن مقادیر در اینپوت
            't_date': {'d': t_day, 'm': t_month, 'y': t_year},
        }

        return render(request, self.template_name, context)


class AdminInviteView(SeniorAdminRequiredMixin, View):
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email')
            perms = data.get('perms', [])
        except:
            return JsonResponse({'status': 'error', 'message': 'Invalid data format'}, status=400)

        if not email:
            return JsonResponse({'status': 'error', 'message': 'Email is required'}, status=400)

        if not perms:
            return JsonResponse({'status': 'error', 'message': 'At least one permission is required.'}, status=400)

        # ۱. ادمین فعلی نباشد
        if AdminUser.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': 'This email is already an admin.'}, status=400)

        # ۲. مدیریت دعوت‌نامه‌های قبلی برای جلوگیری از UNIQUE constraint failed
        # هرگونه دعوت‌نامه قبلی (چه استفاده شده، چه منقضی) را پیدا می‌کنیم
        old_invites = AdminInvitation.objects.filter(email=email)

        if old_invites.exists():
            # اگر دعوت‌نامه "فعال و معتبر" دارد، اجازه ساخت جدید نمی‌دهیم
            active_invite = old_invites.filter(is_used=False).first()
            if active_invite and active_invite.is_valid():  # فرض بر داشتن متد is_valid در مدل
                return JsonResponse({
                    'status': 'error',
                    'message': 'An active invitation already exists for this email.'
                }, status=400)

            old_invites.delete()

        try:
            with transaction.atomic():
                invitation = AdminInvitation.objects.create(
                    email=email,
                    invited_by=request.admin_user,
                    permissions=perms,
                    is_used=False,
                    created_at=timezone.now(),
                    ip_address=self.get_client_ip(request)
                )

                link = request.build_absolute_uri(
                    reverse('admin-complete-registration', kwargs={'token': str(invitation.token)}))

                # ارسال تسک به سلری
                send_admin_invitation_email.delay(email, link)

            return JsonResponse({'status': 'success', 'message': 'Invitation sent successfully.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'System error: {str(e)}'}, status=500)


class AdminDeleteView(SeniorAdminRequiredMixin, View):
    def get(self, request, admin_id):
        admin_to_delete = get_object_or_404(AdminUser, id=admin_id)

        # ۱. بررسی حذف خود (آیا فرد آخرین ادمین است؟)
        if admin_to_delete.id == request.admin_user.id:
            other_admins_exists = AdminUser.objects.exclude(id=admin_to_delete.id).exists()
            if not other_admins_exists:
                return JsonResponse({'success': False,
                                     'message': 'You are the last admin. You cannot delete yourself and leave the system empty.'})

        # ۲. اگر قصد حذف دیگری را دارد یا آخرین ادمین نیست، کد ارسال شود
        if admin_to_delete.id != request.admin_user.id:
            send_delete_otp_task.delay(
                admin_to_delete.id,
                admin_to_delete.email,
                admin_to_delete.username
            )
            return JsonResponse({'success': True, 'message': 'Verification code sent to email.'})

        return JsonResponse({'success': True, 'message': 'Successor selection required.'})

    def post(self, request, admin_id):
        admin_to_delete = get_object_or_404(AdminUser, id=admin_id)

        # سناریو ۱: حذف خود (Self-Deletion)
        if admin_to_delete.id == request.admin_user.id:
            # چک کردن اینکه آیا ادمین دیگری (هر نوعی) وجود دارد یا خیر
            other_admins = AdminUser.objects.exclude(id=admin_to_delete.id)

            if not other_admins.exists():
                return JsonResponse({'success': False, 'message': 'Cannot delete the only administrator.'})

            new_senior_id = request.POST.get('new_senior_id')
            other_seniors = other_admins.filter(is_senior=True)

            # اگر خودش ارشد است و ارشد دیگری باقی نمی‌ماند، حتماً باید جانشین تعیین کند
            if admin_to_delete.is_senior and not other_seniors.exists() and not new_senior_id:
                return JsonResponse(
                    {'success': False, 'message': 'You must promote another admin to Senior before leaving.'})

            try:
                with transaction.atomic():
                    target_email = admin_to_delete.email
                    target_id = admin_to_delete.id

                    log_admin_activity(
                        request,
                        'DELETE',
                        'AdminUser',
                        target_id,
                        f"Admin with email {target_email} has been permanently removed from the system."
                    )

                    if new_senior_id:
                        successor = get_object_or_404(AdminUser, id=new_senior_id)
                        successor.is_senior = True
                        successor.save()

                    admin_to_delete.delete()
                    AdminInvitation.objects.filter(email=target_email).delete()

                # خروج کامل از سیستم
                if request.admin_session:
                    request.admin_session.delete()
                response = JsonResponse({'success': True, 'redirect': '/adminPanel/login/'})
                response.delete_cookie("admin_sessionid")
                return response
            except Exception as e:
                return JsonResponse({'success': False, 'message': 'Process failed.'})

        # سناریو ۲: حذف دیگران با OTP (در این حالت همیشه حداقل یک نفر -یعنی خودِ ادمین فعلی- باقی می‌ماند)
        otp_code = request.POST.get('otp_code')
        cache_key = f"delete_otp_{admin_id}"
        saved_otp = cache.get(cache_key)

        if not otp_code or str(otp_code) != str(saved_otp):
            return JsonResponse({'success': False, 'message': 'Invalid or expired code.'})

        try:
            with transaction.atomic():
                target_email = admin_to_delete.email
                target_id = admin_to_delete.id
                log_admin_activity(
                    request,
                    'DELETE',
                    'AdminUser',
                    target_id,
                    f"Administrator {admin_to_delete.username} was terminated by a Senior Administrator."
                )

                admin_to_delete.delete()
                AdminInvitation.objects.filter(email=target_email).delete()
                cache.delete(cache_key)
            return JsonResponse({'success': True, 'message': 'Admin removed successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': 'Database error.'})


class AdminUpdateView(SeniorAdminRequiredMixin, View):
    def post(self, request, pk):
        target_admin = get_object_or_404(AdminUser, pk=pk)

        # 1. دریافت داده‌ها
        full_name = request.POST.get('full_name', '').strip()
        is_active = request.POST.get('is_active') == 'true'
        is_senior_val = request.POST.get('is_senior') == 'true'
        new_permissions = request.POST.getlist('permissions')

        # 2. بررسی امنیت: جلوگیری از سلب دسترسی ارشد از خود
        if target_admin.id == request.admin_user_id and not is_senior_val:
            return JsonResponse({'status': 'error', 'message': 'You cannot remove your own Senior status.'}, status=400)

        # 3. منطق شرطی OTP
        if target_admin.is_senior:
            otp_input = request.POST.get('otp_code', '').strip()
            cache_key = f'otp_edit_{target_admin.id}'
            cached_otp = cache.get(cache_key)

            if not otp_input or otp_input != str(cached_otp):
                # تولید و ذخیره کد جدید
                new_otp = str(random.randint(100000, 999999))
                cache.set(cache_key, new_otp, 300)

                # ارسال به ایمیل ادمینِ هدف (Target)
                send_admin_edit_otp_task.delay(target_admin.email, new_otp, target_admin.full_name)

                return JsonResponse({
                    'status': 'need_otp',
                    'message': f'Security Alert: A code was sent to {target_admin.username} for confirmation.'
                })

            # کد درست بود؟ پس برای امنیتِ "یک‌بار مصرف"، آن را همین لحظه پاک کن
            cache.delete(cache_key)

        # 4. ذخیره‌سازی نهایی
        try:
            target_admin.full_name = full_name
            target_admin.is_active = is_active
            target_admin.is_senior = is_senior_val
            target_admin.permissions = new_permissions
            target_admin.save()

            return JsonResponse({
                'status': 'success',
                'message': f'Changes for {target_admin.username} applied successfully.'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Error updating database.'}, status=500)


class CompleteRegistrationView(View):
    template_name = 'adminpanel/auth/complete_registration.html'

    def get(self, request, token):
        invitation = get_object_or_404(AdminInvitation, token=token)
        if not invitation.is_valid():
            return render(request, 'errors/link_expired.html', {
                'reason': 'This invitation link has expired or has already been used.'
            })
        return render(request, self.template_name, {'email': invitation.email})

    def post(self, request, token):
        invitation = get_object_or_404(AdminInvitation, token=token)
        form = AdminRegistrationForm(request.POST)

        if not invitation.is_valid():
            return JsonResponse({'status': 'error', 'message': 'Link expired.'}, status=400)

        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    is_senior_invite = "__senior__" in invitation.permissions
                    clean_perms = [p for p in invitation.permissions if p != "__senior__"]

                    # ایجاد اکانت در وضعیت "غیرفعال" برای تایید ثانویه
                    new_admin = AdminUser.objects.create(
                        email=invitation.email,
                        username=data['username'],
                        full_name=data['full_name'],
                        password=make_password(data['password']),
                        permissions=clean_perms,
                        is_active=False,
                        is_staff=True,
                        is_senior=is_senior_invite
                    )

                    invitation.is_used = True
                    invitation.save()

                return JsonResponse({
                    'status': 'success',
                    'message': 'Registration complete! Your account is pending approval by a senior admin.'
                })
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': 'Database error.'}, status=500)

        first_error = list(form.errors.values())[0][0]
        return JsonResponse({'status': 'error', 'message': first_error}, status=400)


class AdminRequestManagerView(SeniorAdminRequiredMixin, View):
    # نمایش لیست
    def get(self, request):
        pending_admins = AdminUser.objects.filter(is_active=False, is_staff=True).order_by('-id')
        return render(request, 'adminpanel/partial/admin_requests_partials.html', {
            'pending_admins': pending_admins
        })

    # عملیات تایید یا رد
    def post(self, request, admin_id):
        action = request.POST.get('action')
        pending_admin = get_object_or_404(AdminUser, id=admin_id, is_active=False)

        try:
            with transaction.atomic():
                if action == 'approve':
                    pending_admin.is_active = True
                    pending_admin.save()

                    # ارسال ایمیل
                    login_url = request.build_absolute_uri(reverse('admin-login'))
                    send_admin_activation_email.delay(pending_admin.email, login_url)

                    # HTMX سطر را حذف می‌کند، پس پاسخ خالی با استاتوس 200 می‌فرستیم
                    return HttpResponse("")

                elif action == 'reject':
                    pending_admin.delete()
                    return HttpResponse("")

            return HttpResponse(status=400)  # خطا در اکشن

        except Exception as e:
            # در صورت خطا، پیام خطا را می‌فرستیم تا در کنسول یا جای دیگر دیده شود
            return HttpResponse(str(e), status=500)


class AdminLogListView(SeniorAdminRequiredMixin, View):
    def get(self, request):
        export_format = request.GET.get('export')  # مقادیر: 'csv' یا 'json'

        if export_format:
            logs = AdminLog.objects.all().select_related('admin').order_by('-created_at')
            filename = f"admin_logs_{timezone.now().strftime('%Y%m%d')}"

            # --- خروجی CSV (مناسب برای اکسل) ---
            if export_format == 'csv':
                response = HttpResponse(content_type='text/csv; charset=utf-8')
                response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
                # نوشتن BOM برای نمایش صحیح کاراکترهای فارسی در اکسل
                response.write(u'\ufeff'.encode('utf8'))

                writer = csv.writer(response)
                writer.writerow(['Admin', 'Action', 'Details', 'IP Address', 'Date Time'])

                for log in logs:
                    writer.writerow([
                        log.admin.username if log.admin else 'System',
                        log.get_action_display(),
                        log.description,
                        log.ip_address,
                        log.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    ])
                return response

            # --- خروجی JSON (مناسب برای پردازش داده) ---
            elif export_format == 'json':
                # تبدیل داده‌ها به لیست دیکشنری
                data = list(logs.values('admin__username', 'action', 'description', 'ip_address', 'created_at'))
                response = JsonResponse(data, safe=False)
                response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
                return response

        # --- بخش نمایش معمولی در مودال (HTMX) ---
        logs = AdminLog.objects.all().select_related('admin').order_by('-created_at')[:50]
        return render(request, 'adminpanel/partial/admin_logs_partial.html', {'logs': logs})


@method_decorator(never_cache, name='dispatch')
class AdminSecuritySettingsView(AdminRequiredMixin, View):
    template_name = 'adminpanel/adminPanel/admin_security_settings.html'
    success_url = reverse_lazy('admin_password')

    def get_context_data(self, user, form=None):
        # 🟢 اصلاح اول: مطمئن می‌شویم سکرت کد در دیتابیس قفل و ذخیره شده تا در متد POST تغییر نکند
        if not user.otp_secret:
            user.otp_secret = pyotp.random_base32()
            user.save(update_fields=['otp_secret'])

        totp = pyotp.totp.TOTP(user.otp_secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name="Admin_Panel")

        img = qrcode.make(uri)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            'form': form or AdminPasswordChangeForm(user=user),
            'qr_b64': qr_b64,
            'secret': user.otp_secret,
            'is_enabled': user.is_otp_enabled,
            'user': user
        }

    def get(self, request):
        # 🟢 اصلاح کلیدی: اجبار جنگو به به‌روزرسانی اطلاعات کاربر مستقیماً از دیتابیس
        request.admin_user.refresh_from_db()

        context = self.get_context_data(request.admin_user)
        return render(request, self.template_name, context)

    def post(self, request):
        user = request.admin_user

        # تشخیص اینکه کدام بخش ارسال شده است
        if 'old_password' in request.POST:
            form = AdminPasswordChangeForm(user=user, data=request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'You have successfully changed your password.')
                return redirect(self.success_url)
            else:
                context = self.get_context_data(user, form=form)
                return render(request, self.template_name, context)

        # اگر درخواست فعال‌سازی 2FA بود
        otp_code = request.POST.get('otp_code')
        if otp_code:
            # تمیز کردن ورودی از هرگونه فاصله احتمالی
            clean_otp = otp_code.replace(' ', '').strip()

            if not user.otp_secret:
                return JsonResponse({'status': 'error', 'message': 'Secret key missing. Please refresh.'})

            totp = pyotp.totp.TOTP(user.otp_secret)

            # 🟢 اصلاح دوم: اضافه کردن valid_window=1 برای حل مشکل اختلاف ساعت گوشی و سرور
            # مقدار 1 به این معنی است که سیستم ۳۰ ثانیه قبل و ۳۰ ثانیه بعد را هم معتبر می‌شناسد
            if totp.verify(clean_otp, valid_window=1):
                user.is_otp_enabled = True
                user.otp_enabled_at = timezone.now()
                user.save(update_fields=['is_otp_enabled', 'otp_enabled_at'])
                return JsonResponse({'status': 'success', 'message': '2FA enabled successfully'})

            return JsonResponse({'status': 'error', 'message': 'Invalid code. Please check your device time.'})

        return JsonResponse({'status': 'error', 'message': 'Invalid request'})

    def delete(self, request):
        user = request.admin_user
        user.refresh_from_db()

        otp_code = request.GET.get('otp_code', '').replace(' ', '').strip()

        if not otp_code:
            return JsonResponse({'status': 'error', 'message': 'Verification code is required.'})

        if not user.otp_secret:
            return JsonResponse({'status': 'error', 'message': 'Invalid security state.'})

        totp = pyotp.totp.TOTP(user.otp_secret)

        if totp.verify(otp_code, valid_window=1):
            user.is_otp_enabled = False
            user.otp_enabled_at = None

            # 🟢 اصلاح: فقط وضعیت فعال بودن را تغییر می‌دهیم،
            # مقدار user.otp_secret را اصلاً دست نمی‌زنیم تا ثابت بماند.
            user.save(update_fields=['is_otp_enabled', 'otp_enabled_at'])

            return JsonResponse({'status': 'success', 'message': '2FA has been disabled successfully.'})

        return JsonResponse({'status': 'error', 'message': 'Invalid code. 2FA remains active.'})


# ---------------- Dashboard managment ----------------

class AdminDashboardView(AdminRequiredMixin, View):
    template_name = 'adminpanel/adminPanel/adminPanel.html'

    @method_decorator(admin_permission_required('wallet'))
    def get(self, request):
        now_utc = timezone.now()
        today_utc_date = now_utc.date()

        # =========================================================================
        # 📊 ۱. ساخت ساب‌کوئری‌های بهینه برای کارت اول (سودآوری پلتفرم از کارمزدها)
        # =========================================================================
        pred_fees_sub = Subquery(
            Prediction.objects.filter(user=OuterRef('pk'), settled=True)
            .values('user')
            .annotate(total=Sum('fee_amount'))
            .values('total'),
            output_field=DecimalField()
        )

        trade_fees_sub = Subquery(
            InternalTrade.objects.filter(user=OuterRef('pk'))
            .values('user')
            .annotate(total=Sum('fee'))
            .values('total'),
            output_field=DecimalField()
        )

        top_earners_qs = User.objects.select_related('profile').annotate(
            p_fees=Coalesce(pred_fees_sub, Decimal('0.00')),
            t_fees=Coalesce(trade_fees_sub, Decimal('0.000000')),
            total_profit=F('p_fees') + F('t_fees')
        ).filter(total_profit__gt=0).order_by('-total_profit')[:6]

        top_earners_list = list(top_earners_qs)

        top_earners = []
        for user in top_earners_list:
            avatar_url = None
            if hasattr(user, 'profile') and user.profile and user.profile.avatar:
                try:
                    avatar_url = user.profile.avatar.url
                except ValueError:
                    avatar_url = None

            top_earners.append({
                'username': user.username,
                'email': user.email,
                'avatar': avatar_url,
                'total_profit': user.total_profit,
                'profit_display': f"${user.total_profit:,.2f}",
                'placeholder': False
            })

        while len(top_earners) < 6:
            top_earners.append({'placeholder': True})

        # =========================================================================
        # ⚡ ۲. ساخت ساب‌کوئری‌های بهینه برای کارت دوم (فعال‌ترین کاربران سیستم)
        # =========================================================================
        it_count_sub = Subquery(
            InternalTrade.objects.filter(user=OuterRef('pk')).values('user').annotate(total=Count('id')).values(
                'total'),
            output_field=IntegerField()
        )
        tx_count_sub = Subquery(
            WalletTransaction.objects.filter(wallet__user=OuterRef('pk')).values('wallet__user').annotate(
                total=Count('id')).values('total'),
            output_field=IntegerField()
        )
        wd_count_sub = Subquery(
            WithdrawRequest.objects.filter(user=OuterRef('pk')).values('user').annotate(total=Count('id')).values(
                'total'),
            output_field=IntegerField()
        )
        pred_count_sub = Subquery(
            Prediction.objects.filter(user=OuterRef('pk')).values('user').annotate(total=Count('id')).values('total'),
            output_field=IntegerField()
        )

        most_active_qs = User.objects.select_related('profile').annotate(
            it_c=Coalesce(it_count_sub, 0),
            tx_c=Coalesce(tx_count_sub, 0),
            wd_c=Coalesce(wd_count_sub, 0),
            pred_c=Coalesce(pred_count_sub, 0),
            total_actions=F('it_c') + F('tx_c') + F('wd_c') + F('pred_c')
        ).filter(total_actions__gt=0).order_by('-total_actions')[:6]

        most_active_list = list(most_active_qs)

        most_active_users = []
        for user in most_active_list:
            avatar_url = None
            if hasattr(user, 'profile') and user.profile and user.profile.avatar:
                try:
                    avatar_url = user.profile.avatar.url
                except ValueError:
                    avatar_url = None

            most_active_users.append({
                'username': user.username,
                'avatar': avatar_url,
                'total_actions': user.total_actions,
                'details': f"Trades: {user.it_c} | Preds: {user.pred_c} | TXs: {user.tx_c}",
                'placeholder': False
            })

        while len(most_active_users) < 6:
            most_active_users.append({'placeholder': True})

        # =========================================================================
        # 👑 استخراج ۲ کاربر برتر پلتفرم برای کارت زنده دکمه‌دار (اصلاح خطای ایندنت)
        # =========================================================================
        top_earner_user = top_earners_list[0] if top_earners_list else None
        most_active_user = most_active_list[0] if most_active_list else None

        highlight_top_earner = None
        if top_earner_user:
            pred_stats = Prediction.objects.filter(user=top_earner_user).aggregate(
                total=Count('id'),
                wins=Count('id', filter=Q(result='win'))
            )
            total_preds = pred_stats['total']
            win_preds = pred_stats['wins']
            win_rate = (win_preds / total_preds * 100) if total_preds > 0 else 0.0

            two_fa_top = False
            if hasattr(top_earner_user, 'two_factor') and top_earner_user.two_factor:
                two_fa_top = getattr(top_earner_user.two_factor, 'is_enabled', False) and getattr(
                    top_earner_user.two_factor, 'is_verified', False)

            highlight_top_earner = {
                'user': top_earner_user,
                'total_profit': top_earner_user.total_profit,
                'win_rate': f"{win_rate:.1f}%",
                'two_fa': two_fa_top,
                'open_tickets': UserTicket.objects.filter(user=top_earner_user, status='open').count()
            }

        highlight_most_active = None
        if most_active_user:
            two_fa_active = False
            if hasattr(most_active_user, 'two_factor') and most_active_user.two_factor:
                two_fa_active = getattr(most_active_user.two_factor, 'is_enabled', False) and getattr(
                    most_active_user.two_factor, 'is_verified', False)

            highlight_most_active = {
                'user': most_active_user,
                'total_predictions': most_active_user.pred_c,
                'total_trades': most_active_user.it_c,
                'two_fa': two_fa_active,
                'open_tickets': UserTicket.objects.filter(user=most_active_user, status='open').count()
            }

        # =========================================================================
        # 🎯 ۳. دیتای کارت سوم: آنالیز حجم و فیلتر زمانی معاملات (Pure UTC Engine)
        # =========================================================================
        time_filter = request.GET.get('sort_activity', 'today')
        filters = {}

        if time_filter == 'today':
            filters['created_at__date'] = today_utc_date
            filter_label = "Today"
        elif time_filter == 'yesterday':
            filters['created_at__date'] = today_utc_date - timedelta(days=1)
            filter_label = "Yesterday"
        elif time_filter == 'week':
            filters['created_at__gte'] = now_utc - timedelta(days=7)
            filter_label = "This Week"
        elif time_filter == 'month':
            filters['created_at__gte'] = now_utc - timedelta(days=30)
            filter_label = "This Month"
        elif time_filter == 'all':
            filter_label = "All Time"
        else:
            filters['created_at__date'] = today_utc_date
            filter_label = "Today"

        trade_summary = InternalTrade.objects.filter(**filters).values('crypto_currency').annotate(
            total_trades=Count('id'),
            total_volume=Sum('total_cost')
        ).order_by('-total_trades')

        popular_trades = []
        for item in trade_summary:
            sym = item['crypto_currency'].upper()
            popular_trades.append({
                'symbol': sym,
                'icon_name': sym.lower(),
                'trade_count': item['total_trades'],
                'volume': item['total_volume'] or Decimal('0.00'),
            })

        # =========================================================================
        # 📊 ۵. مانیتورینگ نقدینگی پلتفرم (پنجره غلتان ۷ روزه بر پایه Pure UTC)
        # =========================================================================
        start_date = today_utc_date - timedelta(days=6)

        active_txs = WalletTransaction.objects.filter(
            status='success',
            timestamp__date__gte=start_date,
            timestamp__date__lte=today_utc_date
        )

        chart_days = [start_date + timedelta(days=i) for i in range(7)]
        chart_categories = [day.strftime('%a') for day in chart_days]

        data_mapping = {day: {'deposit': Decimal('0.000000'), 'withdraw': Decimal('0.000000')} for day in chart_days}

        for tx in active_txs:
            tx_date = tx.timestamp.date()
            if tx_date in data_mapping:
                data_mapping[tx_date][tx.type] += tx.amount

        chart_deposits = [float(data_mapping[day]['deposit']) for day in chart_days]
        chart_withdrawals = [float(data_mapping[day]['withdraw']) for day in chart_days]

        total_deposits_7d = sum(chart_deposits)
        total_withdrawals_7d = sum(chart_withdrawals)
        net_revenue_7d = total_deposits_7d - total_withdrawals_7d
        net_revenue_signal_7d = "+" if net_revenue_7d >= 0 else ""
        net_revenue_class_7d = "text-success" if net_revenue_7d >= 0 else "text-danger"

        today_deps_val = float(data_mapping[today_utc_date]['deposit'])
        today_wths_val = float(data_mapping[today_utc_date]['withdraw'])
        today_net_val = today_deps_val - today_wths_val
        today_net_signal = "+" if today_net_val >= 0 else ""
        today_net_class = "text-success" if today_net_val >= 0 else "text-danger"

        # =========================================================================
        # 🪙 ۶. رادار نقدینگی و تکمیل Context
        # =========================================================================
        platform_assets = get_platform_liquidity_data()

        context = {
            'top_earners': top_earners,
            'most_active_users': most_active_users,
            'popular_trades': popular_trades,
            'current_activity_filter': filter_label,
            'admin_user': request.admin_user,
            'platform_assets': platform_assets,

            'highlight_top_earner': highlight_top_earner,
            'highlight_most_active': highlight_most_active,

            'chart_categories': chart_categories,
            'chart_deposits': chart_deposits,
            'chart_withdrawals': chart_withdrawals,

            'total_deposits_7d': f"${total_deposits_7d:,.2f}",
            'total_withdrawals_7d': f"${total_withdrawals_7d:,.2f}",
            'net_revenue_7d': f"{net_revenue_signal_7d}${net_revenue_7d:,.2f}",
            'net_revenue_class_7d': net_revenue_class_7d,

            'today_deposits': f"${today_deps_val:,.2f}",
            'today_withdrawals': f"${today_wths_val:,.2f}",
            'today_net_revenue': f"{today_net_signal}${today_net_val:,.2f}",
            'today_net_class': today_net_class,
        }

        return render(request, self.template_name, context)


@method_decorator(admin_permission_required('wallet'), name='dispatch')
class ModifyUserBalanceView(AdminRequiredMixin, View):
    """ View to modify user wallet balance and log a formal Notification record """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            email = data.get('email')
            currency_input = data.get('currency', '').lower()
            action = data.get('action')
            amount_str = data.get('amount')
            reason = data.get('reason')

            if not all([email, currency_input, action, amount_str, reason]):
                return JsonResponse({'status': 'error', 'message': 'All fields are required.'}, status=400)

            amount = Decimal(amount_str)
            if amount <= 0:
                return JsonResponse({'status': 'error', 'message': 'Amount must be greater than zero.'}, status=400)

            # نگاشت ارز به فیلد اختصاصی دیتابیس (مانند usdttrc20)
            target_currency = "usdttrc20" if currency_input == "usdt" else currency_input

            with transaction.atomic():
                user = User.objects.filter(email=email).first()
                if not user:
                    return JsonResponse({'status': 'error', 'message': 'User with this email not found.'}, status=404)

                wallet = user.crypto_wallets.filter(currency=target_currency).first()
                if not wallet:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Wallet for currency {currency_input.upper()} ({target_currency}) not found.'
                    }, status=404)

                current_balance = wallet.balance

                # ۱. تحلیل عملیات ادمین و آماده‌سازی متن اعلان شفاف برای کاربر
                if action == 'add':
                    new_balance = current_balance + amount
                    title_text = "Wallet Balance Credited"
                    message_text = f"Your {currency_input.upper()} wallet has been credited with {amount:,.6f} by management. Reason: {reason}"
                elif action == 'deduct':
                    if current_balance < amount:
                        return JsonResponse({'status': 'error', 'message': 'Insufficient user balance.'}, status=400)
                    new_balance = current_balance - amount
                    title_text = "Wallet Balance Adjusted"
                    message_text = f"Your {currency_input.upper()} wallet has been debited by {amount:,.6f} due to systemic corrections. Reason: {reason}"
                else:
                    return JsonResponse({'status': 'error', 'message': 'Invalid action type.'}, status=400)

                # ۲. اعمال فیزیکی تغییرات روی موجودی والت کاربر
                wallet.balance = new_balance
                wallet.save()

                # ۳. 🚀 تزریق مستقیم به دیتابیس اعلان‌های اختصاصی شما (مختص کاربر هدف)
                user_wallet_link = None
                try:
                    user_wallet_link = reverse('wallet_dashboard')  # نام روت صفحه والت کاربر شما
                except Exception:
                    user_wallet_link = "/dashboard/wallet/"  # آدرس‌دهی استاتیک زاپاس

                Notification.objects.create(
                    user=user,
                    admin_recipient=None,  # تهی برای ارسال مستقیم به سایدبار کاربر
                    title=title_text,
                    message=message_text,
                    category='general',  # منطبق بر CATEGORY_CHOICES مدل شما
                    notification_type='alert',  # قرارگیری در فرمت هشدار سیستمی
                    link=user_wallet_link,
                    is_read=False
                )

                return JsonResponse({
                    'status': 'success',
                    'message': 'Balance updated and system notification dispatched successfully.',
                    'new_balance': f"{new_balance:,.6f}"
                })

        except Exception as e:
            print(f"JARVIS BALANCE NOTIFICATION ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': 'Server error during transaction mapping.'}, status=500)


# ---------------- User Management ----------------


class UserManagementListView(SeniorAdminRequiredMixin, ListView):
    """
    نمایش لیست کاربران با قابلیت جستجو و فیلتر بر اساس وضعیت KYC و فعال بودن حساب
    """
    model = User
    template_name = 'adminpanel/Users/user_managment.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().order_by('-date_joined')
        search = self.request.GET.get('search', '')
        kyc_status = self.request.GET.get('kyc_status', '')
        is_active = self.request.GET.get('is_active', '')

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(profile__first_name__icontains=search) |
                Q(profile__last_name__icontains=search)
            ).distinct()

        if kyc_status:
            if kyc_status == 'pending':
                queryset = queryset.filter(profile__approval_status__status='pending')
            elif kyc_status == 'approved':
                queryset = queryset.filter(profile__approval_status__status='approved')
            elif kyc_status == 'rejected':
                queryset = queryset.filter(profile__approval_status__status='rejected')
            elif kyc_status == 'not_submitted':
                queryset = queryset.filter(
                    Q(profile__approval_status__isnull=True) |
                    Q(profile__approval_status__status__isnull=True)
                )

        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # افزودن وضعیت KYC به هر کاربر
        users = context['users']
        for user in users:
            try:
                approval = user.profile.approval_status
                user.kyc_status = approval.status if approval else 'not_submitted'
            except (UserProfile.DoesNotExist, AttributeError):
                user.kyc_status = 'no_profile'
        context.update({
            'search': self.request.GET.get('search', ''),
            'kyc_status': self.request.GET.get('kyc_status', ''),
            'is_active': self.request.GET.get('is_active', ''),
        })
        return context


class UserDetailView(SeniorAdminRequiredMixin, DetailView):
    model = User
    template_name = 'adminpanel/Users/user_details.html'
    context_object_name = 'target_user'
    pk_url_kwarg = 'user_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        profile = getattr(user, 'profile', None)
        approval = ProfileApprovalStatus.objects.filter(profile=profile).first() if profile else None
        ban_history = UserBanHistory.objects.filter(user=user).order_by('-ban_start')

        # ۱. صفحه‌بندی تریدهای داخلی
        trades_list = InternalTrade.objects.filter(user=user).order_by('-created_at')
        trades_paginator = Paginator(trades_list, 5)
        trades_page_number = self.request.GET.get('page', 1)
        try:
            internal_trades = trades_paginator.page(trades_page_number)
        except PageNotAnInteger:
            internal_trades = trades_paginator.page(1)
        except EmptyPage:
            internal_trades = trades_paginator.page(trades_paginator.num_pages)

        # ۲. صفحه‌بندی پیش‌بینی‌ها
        predictions_list = Prediction.objects.filter(user=user).order_by('-created_at')
        predict_paginator = Paginator(predictions_list, 5)
        predict_page_number = self.request.GET.get('predict_page', 1)
        try:
            user_predictions = predict_paginator.page(predict_page_number)
        except PageNotAnInteger:
            user_predictions = predict_paginator.page(1)
        except EmptyPage:
            user_predictions = predict_paginator.page(predict_paginator.num_pages)

        # ۳. صفحه‌بندی شریان‌های مالی
        transactions_list = WalletTransaction.objects.filter(wallet__user=user).order_by('-timestamp')
        finance_paginator = Paginator(transactions_list, 5)
        finance_page_number = self.request.GET.get('finance_page', 1)
        try:
            wallet_transactions = finance_paginator.page(finance_page_number)
        except PageNotAnInteger:
            wallet_transactions = finance_paginator.page(1)
        except EmptyPage:
            wallet_transactions = finance_paginator.page(finance_paginator.num_pages)

        # ۴. تیکت‌های پشتیبانی کاربر (کالیبره شده)
        tickets_queryset = UserTicket.objects.filter(user=user).order_by('-created_at')
        open_tickets = tickets_queryset.filter(status='open')
        answered_tickets = tickets_queryset.filter(status='answered')

        # تزریق به متغیرهای Context
        context['profile'] = profile
        context['approval'] = approval
        context['ban_history'] = ban_history
        context['internal_trades'] = internal_trades
        context['user_predictions'] = user_predictions
        context['wallet_transactions'] = wallet_transactions

        # متغیرهای مربوط به تب پشتیبانی
        context['open_tickets'] = open_tickets
        context['answered_tickets'] = answered_tickets
        context['open_tickets_count'] = open_tickets.count()
        context['answered_tickets_count'] = answered_tickets.count()  # 🌟 کالیبره شد: تامین دیتای مینی‌کارت دوم

        return context


class ToggleUserStatusView(SeniorAdminRequiredMixin, View):
    """
    فعال/غیرفعال کردن حساب کاربری (AJAX)
    """

    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        user.is_active = not user.is_active
        user.save()
        return JsonResponse({'success': True, 'is_active': user.is_active})


class BanUserView(SeniorAdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            is_banned = data.get('is_banned', True)
            ban_reason = data.get('ban_reason', '').strip()

            if not user_id:
                return JsonResponse({'success': False, 'message': 'user_id is required'}, status=400)

            user = get_object_or_404(User, id=user_id)
            profile = user.profile

            if is_banned:
                # ثبت بن جدید
                UserBanHistory.objects.create(
                    user=user,
                    ban_start=timezone.now(),
                    ban_reason=ban_reason,
                    unbanned_at=None  # هنوز آزاد نشده
                )
                profile.is_banned = True
                profile.ban_reason = ban_reason
                profile.ban_start = timezone.now()
                profile.ban_end = None
                profile.save()
                return JsonResponse({'success': True, 'message': f'User {user.username} has been banned.'})
            else:
                # آنبن: پیدا کردن آخرین بن فعال (با unbanned_at = None)
                last_ban = UserBanHistory.objects.filter(user=user, unbanned_at__isnull=True).first()
                if last_ban:
                    last_ban.unbanned_at = timezone.now()
                    last_ban.save()
                # به‌روزرسانی پروفایل
                profile.is_banned = False
                profile.ban_start = None
                profile.ban_end = None
                profile.ban_reason = ''
                profile.save()
                return JsonResponse({'success': True, 'message': f'User {user.username} has been unbanned.'})

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


# ---------------- Profile Approval ----------------

class ProfileApproval(AdminRequiredMixin, View):
    @method_decorator(admin_permission_required('kyc'))
    def get(self, request):
        query = request.GET.get("q", "").strip()

        profiles = ProfileApprovalStatus.objects.select_related('profile__user').all().order_by("-updated_at")

        if query:
            profiles = profiles.filter(
                Q(profile__first_name__icontains=query) |
                Q(profile__last_name__icontains=query) |
                Q(profile__user__email__icontains=query)
            )

        paginator = Paginator(profiles, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {'page_obj': page_obj, 'paginator': paginator, 'query': query}

        return render(request, 'adminpanel/adminPanel/ProfileApproval.html', context)


class ProfileDetailView(AdminRequiredMixin, View):
    template_name = 'adminpanel/adminPanel/ProfileDetail.html'

    @method_decorator(admin_permission_required('kyc'))
    def get(self, request, pk):  # هماهنگ با <int:pk> در urls.py
        profile = get_object_or_404(UserProfile, id=pk)
        status_obj = ProfileApprovalStatus.objects.filter(profile=profile).first()

        return render(request, self.template_name, {
            "profile": profile,
            "approval_status": status_obj.status if status_obj else 'pending',
            "admin_user": request.admin_user
        })


class ProfileApprove(AdminRequiredMixin, View):
    @method_decorator(admin_permission_required('kyc'))
    def get(self, request, pk):
        profile = get_object_or_404(UserProfile, pk=pk)
        status_obj, _ = ProfileApprovalStatus.objects.get_or_create(profile=profile)

        status_obj.status = "approved"
        status_obj.profile_status = "approved"
        status_obj.address_status = "approved"
        status_obj.save()

        profile.status = "approved"
        profile.locked = True
        profile.save()

        Notification.objects.create(
            user=profile.user,
            title="Profile Verified ✅",
            message="Your personal identity has been approved. You now have full access.",
            category='kyc',
            notification_type='message',
        )

        messages.success(request,
                         f"Success: Profile for {profile.user.username} has been verified successfully, You now have full access.")
        return redirect("profile-approval")


class ProfileReject(AdminRequiredMixin, View):
    @method_decorator(admin_permission_required('kyc'))
    def get(self, request, pk):
        profile = get_object_or_404(UserProfile, pk=pk)
        status_obj, _ = ProfileApprovalStatus.objects.get_or_create(profile=profile)

        status_obj.status = "rejected"
        status_obj.profile_status = "rejected"
        status_obj.address_status = "rejected"
        status_obj.save()
        profile.status = "rejected"
        profile.locked = False
        profile.save()

        Notification.objects.create(
            user=profile.user,
            title="Profile Rejected ❌",
            message="Your information was rejected by admin. Please check and resubmit.",
            category='kyc',
            notification_type='alert',
        )

        messages.warning(request, f"Profile {profile.user.username} has been rejected. Please check and resubmit.")
        return redirect("profile-approval")


class DeleteProfiles(AdminRequiredMixin, View):
    @method_decorator(admin_permission_required('kyc'))
    def post(self, request):
        data = json.loads(request.body)
        ids = data.get("ids", [])
        if ids:
            UserProfile.objects.filter(id__in=ids).delete()
            return JsonResponse({"success": True})
        return JsonResponse({"success": False})


# ---------------- Withdraw Requests ----------------

class UserWithdrawRequest(AdminRequiredMixin, View):
    template_name = 'adminpanel/adminPanel/WithdrawRequest.html'

    @method_decorator(admin_permission_required('wallet'))
    def get(self, request):
        # ... متد get بدون تغییر باقی می‌ماند ...
        query = request.GET.get('search', '').strip()
        withdraw_list = WithdrawRequest.objects.all().order_by('-created_at')
        if query:
            withdraw_list = withdraw_list.filter(
                Q(wallet__user__email__icontains=query) |
                Q(tx_hash__icontains=query) |
                Q(target_address__icontains=query)
            )
        paginator = Paginator(withdraw_list, 10)
        page_number = int(request.GET.get('page', 1))
        page_obj = paginator.get_page(page_number)
        total_pages = paginator.num_pages
        page_range = range(max(page_number - 1, 1), min(page_number + 1, total_pages) + 1)
        context = {
            "page_obj": page_obj,
            "withdraw_list": page_obj.object_list,
            "page_range": page_range,
            "start_index": page_obj.start_index(),
            "admin_user": request.admin_user,
            "search_query": query
        }
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string(self.template_name, context, request=request)
            return JsonResponse({'html': html})
        return render(request, self.template_name, context)

    @method_decorator(admin_permission_required('wallet'))
    def post(self, request):
        withdraw_id = request.POST.get('withdraw_id')
        tx_code = request.POST.get('tx_code', '').strip()

        if withdraw_id is not None:
            try:
                withdraw = WithdrawRequest.objects.get(id=withdraw_id)

                # ۱. هش بلاکچین با موفقیت در مدل درخواست برداشت ذخیره می‌شود
                withdraw.tx_hash = tx_code
                withdraw.save()

                # 🌟 کالیبره شد: خطای آپدیت تراکنش حذف شد.
                # نیازی به آپدیت در این مرحله نیست؛ چرخه‌ی نهایی تراکنش
                # توسط متد AdminWithdrawActionView و هنگام فشردن دکمه Done تکمیل می‌شود.

                return JsonResponse({'success': True, 'tx_hash': tx_code})
            except WithdrawRequest.DoesNotExist:
                return JsonResponse({'success': False, 'msg': 'Withdraw not found'})


class AdminWithdrawActionView(AdminRequiredMixin, View):
    @method_decorator(admin_permission_required('wallet'))
    def post(self, request, withdraw_id):
        withdraw = get_object_or_404(WithdrawRequest, id=withdraw_id)
        action = request.POST.get("action")
        admin_note = request.POST.get("admin_note", "")

        try:
            with transaction.atomic():
                wallet = DollarWallet.objects.select_for_update().get(id=withdraw.wallet.id)
                tx = WalletTransaction.objects.filter(wallet=wallet, type="withdraw", withdraw=withdraw).first()

                if withdraw.status in ["Done", "approved", "rejected"]:
                    return JsonResponse({"status": "warning", "msg": "This request is already processed."})

                withdraw.processed_by = request.admin_user
                withdraw.processed_at = timezone.now()
                withdraw.admin_note = admin_note

                target_url = reverse('buy-and-sell')
                # پاکسازی صفرهای اضافی عدد
                formatted_amount = f"{withdraw.amount.normalize():f}"
                # قبل از شروع شرط‌ها:
                note_display = f"\n**Admin Note:** {admin_note.strip()}" if admin_note.strip() else "\n**Admin Note:** No additional comments provided."
                if action == "Done":
                    if not withdraw.tx_hash or withdraw.tx_hash == "":
                        return JsonResponse({"status": "error", "msg": "TX Hash is missing."})

                    # کسر کل مبلغ (اصل + کارمزد) از فریز
                    if wallet.frozen_balance >= withdraw.total_amount:
                        wallet.frozen_balance -= withdraw.total_amount
                        wallet.save()

                    # 🌟 اصلاح: واریز کارمزد به خزانه (فقط یک بار انجام شود)
                    revenue_acc = PlatformRevenue.get_revenue_account()

                    # محاسبه بالانس قبل و بعد برای ژورنال
                    balance_before = revenue_acc.balance
                    revenue_acc.balance += withdraw.fee
                    revenue_acc.save()

                    # ثبت در ژورنال مالی
                    RevenueJournal.objects.create(
                        account=revenue_acc,
                        amount=withdraw.fee,
                        balance_before=balance_before,
                        balance_after=revenue_acc.balance,
                        user_email=withdraw.wallet.user.email
                    )

                    withdraw.status = "Done"
                    withdraw.confirmed = True
                    withdraw.save()

                    if tx:
                        tx.status = "success"
                        tx.confirmed = True
                        tx.tx_hash = withdraw.tx_hash
                        tx.save()

                    # --- ساختار مرتب شده برای تایید (Done) ---
                    notification_message = (
                        f"✅ **Withdrawal Confirmed**\n"
                        f"**Amount:** ${formatted_amount}\n"
                        f"---------------------------\n"
                        f"Your request has been approved. Transaction Hash: `{withdraw.tx_hash[:16]}...`"
                        f"{note_display}"
                    )

                    # --- کالیبراسیون برای وضعیت تایید ---
                    Notification.objects.create(
                        user=withdraw.wallet.user,
                        title="Withdrawal Successful",
                        message=notification_message,
                        category='withdraw',  # اضافه کردن دسته‌بندی برای شناسایی در رادار
                        notification_type='message',
                        link=target_url
                    )

                    messages.success(request, notification_message, extra_tags="withdraw")

                    msg = f"Withdrawal finalized by {request.admin_user.username}."
                    # قبل از شروع شرط‌ها:

                elif action == "reject":
                    wallet.frozen_balance -= withdraw.total_amount
                    wallet.balance += withdraw.total_amount
                    wallet.save()

                    withdraw.status = "rejected"
                    withdraw.confirmed = False
                    withdraw.save()

                    if tx:
                        tx.status = "failed"
                        tx.confirmed = False
                        tx.save()

                    # --- ساختار مرتب شده برای رد (Reject) ---
                    notification_message = (
                        f"❌ **Withdrawal Rejected**\n"
                        f"**Amount:** ${formatted_amount}\n"
                        f"---------------------------\n"
                        f"Funds have been returned to your account."
                        f"{note_display}"
                    )

                    # --- کالیبراسیون برای وضعیت رد ---
                    Notification.objects.create(
                        user=withdraw.wallet.user,
                        title="Withdrawal Rejected",
                        message=notification_message,
                        category='withdraw',  # اضافه کردن دسته‌بندی
                        notification_type='alert',
                        link=target_url
                    )

                    messages.error(request, notification_message, extra_tags="withdraw")

                    msg = f"Rejected by {request.admin_user.username}. Funds returned to user."

                else:
                    return JsonResponse({"status": "error", "msg": "Invalid action"})

        except Exception as e:
            return JsonResponse({"status": "error", "msg": f"System Error: {str(e)}"})

        # منطق رندرینگ (بدون تغییر)
        withdraw_list = WithdrawRequest.objects.all().order_by('-created_at')
        paginator = Paginator(withdraw_list, 15)
        page_obj = paginator.get_page(request.GET.get('page', 1))

        html = render_to_string('adminpanel/adminPanel/WithdrawRequest.html', {
            'page_obj': page_obj,
            'page_range': range(max(page_obj.number - 1, 1), min(page_obj.number + 2, paginator.num_pages + 1)),
            'start_index': page_obj.start_index(),
            'admin_user': request.admin_user
        }, request=request)

        return JsonResponse({"status": "ok", "msg": msg, "html": html})


# ---------------- Tickets ----------------

class AdminTicketListView(AdminRequiredMixin, View):
    template_name = 'adminpanel/tickets/all-tickets.html'

    @method_decorator(admin_permission_required('support'))
    def get(self, request):
        search_query = request.GET.get('search', '')
        tickets = UserTicket.objects.all().order_by('-created_at')

        if search_query:
            tickets = tickets.filter(
                Q(ticket_id__icontains=search_query) |
                Q(title__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )

        paginator = Paginator(tickets, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        current_page = page_obj.number
        total_pages = paginator.num_pages
        start_page = max(current_page - 1, 1)
        end_page = min(current_page + 1, total_pages)
        page_range = range(start_page, end_page + 1)

        context = {
            'tickets': page_obj,
            'page_obj': page_obj,
            'page_range': page_range,
            'search_query': search_query,
            'admin_user': request.admin_user
        }
        return render(request, self.template_name, context)


class AdminTicketDetailView(AdminRequiredMixin, View):
    template_name = 'adminpanel/tickets/ticket-reply.html'

    @method_decorator(admin_permission_required('support'))
    def get(self, request, ticket_id):
        ticket = get_object_or_404(UserTicket, id=ticket_id)

        # JARVIS: به محض باز شدن صفحه توسط ادمین، نوتیفیکیشن خوانده شود
        if hasattr(request, 'admin_user'):
            Notification.objects.filter(
                admin_recipient=request.admin_user,
                link__icontains=str(ticket_id),
                is_read=False
            ).update(is_read=True)

        replies = TicketReply.objects.filter(ticket=ticket).order_by('-created_at')
        return render(request, self.template_name,
                      {'ticket': ticket, 'replies': replies, 'admin_user': request.admin_user})

    @method_decorator(admin_permission_required('support'))
    def post(self, request, ticket_id):
        ticket = get_object_or_404(UserTicket, id=ticket_id)

        # JARVIS: پروتکل جلوگیری از پاسخ مجدد
        if ticket.status == 'answered':
            # می‌توانید اینجا یک پیام خطا هم به سیستم اضافه کنید (messages.error)
            return redirect('admin_ticket_detail', ticket_id=ticket.id)

        message = request.POST.get('message')

        if message:
            # ۱. ثبت پاسخ ادمین
            TicketReply.objects.create(
                ticket=ticket,
                admin_sender=request.admin_user,
                message=message
            )

            # ۲. آپدیت وضعیت تیکت به پاسخ داده شده
            ticket.status = 'answered'
            ticket.save()

        return redirect('admin_ticket_detail', ticket_id=ticket.id)


# ---------------- Logout ----------------
class AdminLogoutView(View):
    def get(self, request):
        admin_key = request.COOKIES.get("admin_sessionid")

        if admin_key:
            try:
                session = SessionStore(session_key=admin_key)
                # پاک کردن کامل سشن از دیتابیس
                session.delete()
            except:
                pass

        response = redirect("admin-login")
        response.delete_cookie("admin_sessionid")
        return response


class AdminLockScreenView(View):
    template_name = 'adminpanel/Lock-screen/admin-lock-screen.html'

    def get(self, request):
        if not getattr(request, "admin_session", None):
            return redirect('admin-login')

        # قفل ادمین روی get فعال می‌شود
        request.admin_session['locked'] = True
        request.admin_session.save()

        form = AdminLockScreen()
        admin_user_id = request.admin_session.get('admin_user_id')  # ← درست
        admin_user = AdminUser.objects.get(id=admin_user_id)
        return render(request, self.template_name, {'form': form, 'admin_user': admin_user})

    def post(self, request):
        if not getattr(request, "admin_session", None):
            return JsonResponse({'success': False, 'error': 'Admin session not found'})

        try:
            data = json.loads(request.body)
            password = data.get('password', '').strip()

            admin_user_id = request.admin_session.get('admin_user_id')
            if not admin_user_id:
                return JsonResponse({'success': False, 'error': 'Admin not logged in'})

            admin_user = AdminUser.objects.get(id=admin_user_id)

            if admin_user.check_password(password):
                request.admin_session['locked'] = False
                request.admin_session.save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Incorrect password'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


@method_decorator(admin_permission_required('prediction'), name='dispatch')
class AdminRoundListView(AdminRequiredMixin, ListView):
    model = PredictionRound
    template_name = "adminpanel/prediction/admin-round-list.html"
    context_object_name = "rounds"
    ordering = ["-start_at"]

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # فرم را با داده‌های POST قبلی (در صورت خطا) یا خالی مقداردهی می‌کنیم
        context['form'] = AdminPredictionRoundForm()
        context['admin_user'] = self.request.admin_user
        return context


class AdminRoundCreateView(AdminRequiredMixin, CreateView):
    model = PredictionRound
    form_class = AdminPredictionRoundForm
    template_name = "adminpanel/prediction/admin-round-list.html"
    success_url = reverse_lazy("admin-round-list")

    @method_decorator(admin_permission_required('prediction'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        assets = form.cleaned_data["assets"]
        fee = form.cleaned_data["admin_fee_percent"]
        now = timezone.now()

        min_limit = form.cleaned_data['min_bet_amount']
        max_limit = form.cleaned_data['max_bet_amount']
        title_from_form = form.cleaned_data.get("title")

        # تابع کمکی برای تبدیل واحدها به ثانیه
        def get_seconds(val, unit):
            if not val: return 0
            return int(val) * 60 if unit == "minutes" else int(val)

        # 🛡️ استخراج تمام تایم‌فریم‌ها
        tf1 = get_seconds(form.cleaned_data.get("tf1_value"), form.cleaned_data.get("tf1_unit"))
        tf2 = get_seconds(form.cleaned_data.get("tf2_value"), form.cleaned_data.get("tf2_unit"))
        tf3 = get_seconds(form.cleaned_data.get("tf3_value"), form.cleaned_data.get("tf3_unit"))
        tf4 = get_seconds(form.cleaned_data.get("tf4_value"), form.cleaned_data.get("tf4_unit"))

        for asset in assets:
            live_price = get_live_price(asset.symbol)

            if not live_price or live_price <= 0:
                form.add_error(None, f"Market Price for {asset.symbol} is unavailable.")
                return self.form_invalid(form)

            last_round = PredictionRound.objects.filter(asset=asset).order_by("-sequence_number").first()
            seq = last_round.sequence_number + 1 if last_round else 1

            # ایجاد راند با تمام مقادیر تایم‌فریم
            new_round = PredictionRound.objects.create(
                asset=asset,
                title=title_from_form or f"{asset.symbol} Trading Round {seq}",
                status="active",
                start_at=now,
                sequence_number=seq,
                current_tf=1,
                current_tf_start_at=now,
                # ذخیره سازی تمام ستون‌ها در دیتابیس 🛡️
                tf1_seconds=tf1,
                tf2_seconds=tf2,
                tf3_seconds=tf3,
                tf4_seconds=tf4,
                # تایم‌فریم جاری (شروع با TF1)
                timeframe_seconds=tf1,
                price_open=live_price,
                min_bet_amount=min_limit,
                max_bet_amount=max_limit,
                admin_fee_percent=fee
            )

            # زمان‌بندی اجرای تسک بعدی
            from Prediction.tasks import advance_timeframe
            advance_timeframe.apply_async(
                args=[new_round.id],
                eta=now + timedelta(seconds=tf1)
            )

        messages.success(self.request, "All rounds started successfully.")
        return redirect(self.success_url)


class AdminRoundUpdateView(AdminRequiredMixin, UpdateView):
    model = PredictionRound
    form_class = AdminPredictionRoundForm
    template_name = "adminpanel/prediction/admin-round-list.html"
    success_url = reverse_lazy("admin-round-list")

    @method_decorator(admin_permission_required('prediction'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        round_obj = form.save(commit=False)
        tf_seconds = form.cleaned_data['timeframes'][0]
        round_obj.timeframes_json = [tf_seconds]
        round_obj.timeframe = tf_seconds
        round_obj.end_at = round_obj.start_at + timedelta(seconds=tf_seconds)
        round_obj.save()
        return redirect(self.success_url)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return self.render_to_response(context)


class AdminRoundDeleteView(AdminRequiredMixin, DeleteView):
    model = PredictionRound
    success_url = reverse_lazy("admin-round-list")

    @method_decorator(admin_permission_required('prediction'))
    def dispatch(self, request, *args, **kwargs):
        # حذف مستقیم با متد POST بدون نیاز به تاییدیه در صفحه جداگانه
        return self.post(request, *args, **kwargs)


@admin_permission_required('prediction')
def round_duration(request, round_id):
    try:
        round_obj = get_object_or_404(PredictionRound, id=round_id)
        return JsonResponse(round_obj.to_dict_for_frontend())
    except PredictionRound.DoesNotExist:
        return JsonResponse({"id": None, "status": "missing", "remaining_seconds": 0})


def error_403_view(request, exception=None):
    return render(request, 'errors/403.html', status=403)
