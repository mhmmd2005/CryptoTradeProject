from django.contrib.auth.backends import BaseBackend

from .models import AdminUser


class AdminUserBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = AdminUser.objects.get(email=username)
            if user.check_password(password) and user.is_active and user.is_staff:
                return user
        except AdminUser.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return AdminUser.objects.get(pk=user_id)
        except AdminUser.DoesNotExist:
            return None
