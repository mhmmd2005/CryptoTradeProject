from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.http import JsonResponse
from django.shortcuts import redirect


class KYCRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        profile = getattr(request.user, 'profile', None)
        is_approved = False

        if profile:
            status_obj = getattr(profile, 'approval_status', None)
            is_approved = (status_obj.status == 'approved') if status_obj else (profile.status == 'approved')

        # ۱. ذخیره برای سایدبار (نمایش پیام کنار ماوس)
        request.user.is_kyc_verified = is_approved

        # ۲. اگر کاربر تایید نشده است:
        if not is_approved:
            # الف) اگر درخواست AJAX/API بود (بلاک کردن عملیات ترید و غیره)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({"status": "error", "message": "نیاز به تایید هویت"}, status=403)

            # ب) اگر کاربر خواست مستقیم آدرس صفحه را تایپ کند (بلاک کردن ورود به صفحه)
            # استثنا: اجازه بده کاربر همیشه صفحه پروفایل خودش را ببیند تا مدارک بفرستد
            # In mixins.py
            if request.resolver_match.url_name != 'profile-setting':
                messages.warning(request,
                                 "Access Restricted! Please complete your identity verification in the 'Personal Details' section.")
                return redirect("dashboard:profile-setting")

        return super().dispatch(request, *args, **kwargs)


# --- اضافه کردن دکوریتور برای توابع ---
def kyc_required_decorator(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('login')

        profile = getattr(user, 'profile', None)
        status = "pending"
        if profile:
            status_obj = getattr(profile, "approval_status", None)
            status = status_obj.status if status_obj else profile.status

        if status == "approved":
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "دسترسی محدود! ابتدا مدارک خود را تکمیل کنید.")
            return redirect("dashboard:profile-setting")

    return _wrapped_view
