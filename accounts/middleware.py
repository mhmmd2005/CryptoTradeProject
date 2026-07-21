from django.contrib import messages
from django.shortcuts import redirect
from django.urls import resolve


class LockScreenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # مسیرهای پنل ادمین را بررسی نکن
        if request.path.startswith("/adminPanel"):
            return self.get_response(request)

        allowed_view_names = [
            'lock_screen',
            'logout',
            'login',
        ]

        if hasattr(request, 'user') and request.user.is_authenticated:
            locked = request.session.get('locked', False)

            try:
                current_view_name = resolve(request.path_info).view_name
            except:
                current_view_name = None

            if locked and current_view_name not in allowed_view_names:
                # فقط کاربر عادی را ریدایرکت کن
                if current_view_name != 'lock_screen':
                    if not any(
                            msg.message == "🚫 You must unlock the screen first."
                            for msg in messages.get_messages(request)
                    ):
                        messages.warning(
                            request,
                            "🚫 You must unlock the screen first.",
                            extra_tags='lock_screen'
                        )
                    return redirect('lock_screen')

        return self.get_response(request)
