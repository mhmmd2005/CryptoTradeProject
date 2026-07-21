import pyotp

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import User
from django.db import models


# Create your models here.

class User(AbstractUser):
    is_verified = models.BooleanField(default=False)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='accounts_profile')
    otp_secret = models.CharField(max_length=50, blank=True, null=True)
    two_factor_verified = models.BooleanField(default=False)

    def get_totp_uri(self):
        """برمی‌گردونه لینک برای Google Authenticator"""
        if not self.otp_secret:
            self.otp_secret = pyotp.random_base32()
            self.save(update_fields=["otp_secret"])
        return pyotp.TOTP(self.otp_secret).provisioning_uri(
            name=self.user.email,
            issuer_name="MyWebsite"
        )


