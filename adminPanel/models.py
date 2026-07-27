import uuid
from datetime import timedelta
from decimal import Decimal

import pyotp
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group, Permission
from django.core.signing import Signer, BadSignature
from django.db import models
from django.utils import timezone

from Prediction.models import Prediction
from UserPanel.models import UserTicket


# Create your models here.

class TicketReply(models.Model):
    ticket = models.ForeignKey(UserTicket, on_delete=models.CASCADE, related_name='replies')
    admin_sender = models.ForeignKey('adminPanel.AdminUser', on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply to Ticket #{self.ticket.id}"


class AdminUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email must be provided')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        # امضای کلید اولیه OTP پیش از ذخیره‌سازی اولیه
        signer = Signer()
        raw_secret = pyotp.random_base32()
        user.otp_secret = signer.sign(raw_secret)

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_senior', True)
        return self.create_user(email, password, **extra_fields)


class AdminUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    username = models.CharField(max_length=50, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    otp_secret = models.CharField(max_length=128)  # افزایش طول جهت ذخیره کلید امضا شده
    is_otp_enabled = models.BooleanField(default=False)
    otp_enabled_at = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(auto_now_add=True)
    is_senior = models.BooleanField(default=False)

    groups = models.ManyToManyField(Group, blank=True, related_name='admin_users')
    user_permissions = models.ManyToManyField(Permission, blank=True, related_name='admin_users_permissions')
    permissions = models.JSONField(default=list, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = AdminUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name', 'username']

    def save_otp_secret(self, raw_secret):
        signer = Signer()
        self.otp_secret = signer.sign(raw_secret)
        self.save(update_fields=['otp_secret'])

    def get_unmasked_otp_secret(self):
        signer = Signer()
        try:
            return signer.unsign(self.otp_secret)
        except (BadSignature, TypeError):
            return None

    def delete(self, *args, **kwargs):
        # فقط اگر ادمینی که حذف می‌شود "فعال" باشد، تعداد کل ادمین‌های فعال بررسی می‌شود
        if self.is_active:
            active_admins_count = AdminUser.objects.filter(is_active=True).exclude(pk=self.pk).count()
            if active_admins_count < 1:
                raise ValidationError("Critical Error: Cannot delete the last remaining active administrator.")
        super().delete(*args, **kwargs)

    def deactivate_user(self):
        """غیرفعال‌سازی ایمن ادمین با کنترل دقیق Edge Case کاربر از قبل غیرفعال"""
        if not self.is_active:
            return  # کاربر از قبل غیرفعال است

        active_admins_count = AdminUser.objects.filter(is_active=True).exclude(pk=self.pk).count()
        if active_admins_count < 1:
            raise ValidationError("Action Denied: At least one active administrator is required for system stability.")

        self.is_active = False
        self.save(update_fields=['is_active'])

    def __str__(self):
        name_display = f"{self.full_name[:12]}.." if self.full_name else "N/A"
        senior_badge = " [SENIOR]" if self.is_senior else ""
        perms_count = len(self.permissions) if self.permissions else 0
        return f"@{self.username} | {name_display}{senior_badge} | Privileges: {perms_count}"


class AdminLog(models.Model):
    ACTION_CHOICES = [
        ('LOGIN', 'login'),
        ('LOGOUT', 'logout'),
        ('CREATE', 'create'),
        ('UPDATE', 'update'),
        ('DELETE', 'delete'),
        ('FAILED_LOGIN', 'failed_login'),
    ]

    admin = models.ForeignKey('AdminUser', on_delete=models.SET_NULL, null=True, related_name='logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=50, null=True, blank=True)
    object_id = models.CharField(max_length=64, null=True, blank=True)  # پشتیبانی از UUID و Int
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin} - {self.action} - {self.created_at}"


class PlatformRevenue(models.Model):
    title = models.CharField(max_length=50, default="Platform Revenue Account")
    balance = models.DecimalField(
        max_digits=30,
        decimal_places=8,  # اصلاح اعشار به ۸ جهت تطابق کامل با کریپتوکارنسی‌ها
        default=Decimal("0.00000000")
    )
    updated_at = models.DateTimeField(auto_now=True)
    currency = models.CharField(max_length=20, unique=True, default='usdttrc20', verbose_name="currency code")

    def __str__(self):
        return f"{self.currency.upper()} Revenue - Balance: {self.balance}"

    @classmethod
    def get_revenue_account(cls, currency_code='usdttrc20'):
        obj, created = cls.objects.get_or_create(currency=currency_code.lower())
        return obj


class RevenueJournal(models.Model):
    account = models.ForeignKey(PlatformRevenue, on_delete=models.CASCADE, related_name="journals")
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    balance_before = models.DecimalField(max_digits=20, decimal_places=8)  # اصلاح اعشار به ۸
    balance_after = models.DecimalField(max_digits=20, decimal_places=8)  # اصلاح اعشار به ۸

    prediction = models.ForeignKey(Prediction, on_delete=models.SET_NULL, null=True, blank=True)
    user_email = models.EmailField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at',)


class AdminWithdrawal(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    admin = models.ForeignKey('AdminUser', on_delete=models.PROTECT, related_name='withdrawals')
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    destination_wallet = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    currency = models.CharField(max_length=20, default='usdttrc20')

    approved_by = models.ForeignKey('AdminUser', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approvals')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AdminInvitation(models.Model):
    email = models.EmailField(unique=True)
    invited_by = models.ForeignKey(AdminUser, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    permissions = models.JSONField(default=list, blank=True)

    def is_valid(self):
        if self.is_used:
            return False
        return timezone.now() < (self.created_at + timedelta(hours=1))

    def __str__(self):
        return f"Invitation for {self.email} - Valid: {self.is_valid()}"
