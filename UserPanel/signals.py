from django.db.models.signals import post_save
from django.dispatch import receiver

from dashboard.models import Notification, UserProfile
from .tasks import send_email_task


@receiver(post_save, sender=Notification)
def send_email_on_notification(sender, instance, created, **kwargs):
    if created:
        # استفاده از related_name برای دسترسی مستقیم
        try:
            profile = instance.user.profile

            # ارسال ایمیل در صورت فعال بودن و داشتن ایمیل معتبر
            if profile.email_notifications_enabled and instance.user.email:
                send_email_task.delay(
                    subject="New Notification from CryptoTrade",
                    message=instance.message,
                    recipient_list=[instance.user.email]
                )
        except (UserProfile.DoesNotExist, AttributeError):
            pass
