from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AdminUser, AdminWallet


@receiver(post_save, sender=AdminUser)
def create_admin_wallet(sender, instance, created, **kwargs):
    """
        هر بار که یک ادمین جدید ساخته می‌شود، این تابع به صورت خودکار
        یک کیف پول برای او ایجاد می‌کند.
        """
    if created:
        AdminWallet.objects.get_or_create(user=instance)
