import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect


class StrictSessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_time = time.time()
            last_activity = request.session.get('last_activity', current_time)

            timeout = getattr(settings, 'SESSION_COOKIE_AGE', 1800)

            # اگر زمان غیرفعالی بیش از ۳۰ دقیقه شده باشد
            if current_time - last_activity > timeout:
                logout(request)
                return redirect('login')  # 👈 اصلاح نام آدرس به login

            # اگر درخواست عادی باشد (غیر از keep-alive)، زمان فعالیت به‌روزرسانی می‌شود
            if not request.path.endswith('/keep-alive/'):
                request.session['last_activity'] = current_time

        response = self.get_response(request)
        return response
