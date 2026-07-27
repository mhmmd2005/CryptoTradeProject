from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse

User = get_user_model()
from accounts.models import User
from adminPanel.models import AdminUser


# Create your models here.
# مدل پروفایل


class UserProfile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    joining_date = models.DateField(auto_now_add=True, null=True, blank=True)

    # نال‌پذیر کردن شهر و کشور جهت جلوگیری از کرش هنگام ساخت اتوماتیک پروفایل در سیگنال‌ها
    city = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=50, null=True, blank=True)
    zipcode = models.CharField(max_length=30, null=True, blank=True)
    description = models.TextField(blank=True, null=True)

    # یکپارچه‌سازی تصویر آواتار (حذف فیلد تکراری profile_image)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending', db_index=True)
    locked = models.BooleanField(default=False)
    email_notifications_enabled = models.BooleanField(default=False)

    # مدیریت بن شدن کاربر
    is_banned = models.BooleanField(default=False)
    ban_start = models.DateTimeField(null=True, blank=True)
    ban_end = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True, null=True)

    custom_username = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Custom Username"
    )

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.user.username


class UserBanHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ban_history')
    ban_start = models.DateTimeField()
    ban_reason = models.TextField()
    unbanned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ban_start']

    def __str__(self):
        return f"{self.user.username} banned on {self.ban_start}"


class UserBanHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ban_history')
    ban_start = models.DateTimeField()
    ban_reason = models.TextField()
    unbanned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ban_start']

    def __str__(self):
        return f"{self.user.username} banned on {self.ban_start}"


class ProfileApprovalStatus(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='approval_status'
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.profile.user.username} - {self.status}"


class Notification(models.Model):
    TYPE_CHOICES = (
        ('message', 'Message'),
        ('alert', 'Alert'),
    )

    CATEGORY_CHOICES = (
        ('ticket', 'Ticket System'),
        ('withdraw', 'Withdrawal Process'),
        ('deposit', 'Deposit System'),
        ('kyc', 'KYC Verification'),
        ('general', 'General Notification'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_notifications',
        null=True,
        blank=True
    )
    admin_recipient = models.ForeignKey(
        'adminPanel.AdminUser',
        on_delete=models.CASCADE,
        related_name='admin_notifications',
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255, db_index=True)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', db_index=True)
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='message')
    link = models.CharField(max_length=500, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        db_table = 'dashboard_notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username if self.user else 'Admin'} - {self.title}"

    def get_absolute_url(self):
        if self.link:
            return self.link
        return reverse('dashboard:notifications_dropdown')


class InternalTrade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('BUY', 'Buy Asset'),
        ('SELL', 'Sell Asset'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='internal_trades')
    crypto_currency = models.CharField(max_length=10)
    trade_type = models.CharField(max_length=4, choices=TRADE_TYPE_CHOICES)

    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=18, decimal_places=4)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0.0000'))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} | {self.trade_type} {self.amount} {self.crypto_currency.upper()}"

    def get_absolute_url(self):
        return reverse('dashboard:internal-trade-history')
