from django.contrib.sessions.backends.db import SessionStore
from django.shortcuts import redirect
from django.urls import resolve


class AdminPanelCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/adminPanel"):
            admin_key = request.COOKIES.get("admin_sessionid")
            if admin_key:
                session = SessionStore(session_key=admin_key)
                if "admin_user_id" in session:
                    session.set_expiry(1800)
                    session.save()
                request.admin_session = session
            else:
                request.admin_session = None
        else:
            request.admin_session = None
        return self.get_response(request)


# 3. Middleware برای صفحه قفل (Lock Screen)
class AdminLockScreenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed_views = ['admin-login', 'admin-lock-screen', 'admin-logout']
        if getattr(request, "admin_session", None):
            locked = request.admin_session.get("locked", False)
            try:
                current_view = resolve(request.path_info).view_name
            except:
                current_view = None
            if locked and current_view not in allowed_views:
                return redirect("admin-lock-screen")
        return self.get_response(request)
