from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Profile

# Using get_user_model() instead of direct User import
# to ensure compatibility with custom user models.
User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Signal to automatically create a Profile instance
    whenever a new User is registered.
    """
    if created:
        Profile.objects.create(user=instance)
