# UserPanel/middleware.py (یا هر جای دیگری که قرار دارد)
from django.shortcuts import redirect
from django.urls import reverse


class BanUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # مسیرهای پنل ادمین را معاف کن
        if request.path.startswith('/adminPanel/'):
            return self.get_response(request)

        # بررسی وجود attribute user
        if hasattr(request, 'user') and request.user.is_authenticated:
            # کاربران ادمین (staff/superuser) را معاف کن (اختیاری)
            if request.user.is_staff or request.user.is_superuser:
                return self.get_response(request)

            profile = getattr(request.user, 'profile', None)
            if profile and profile.is_banned:
                allowed_paths = [
                    reverse('banned_page'),
                    reverse('logout'),
                    reverse('create_support_ticket'),
                ]
                if request.path not in allowed_paths:
                    return redirect('banned_page')
        response = self.get_response(request)
        return response
