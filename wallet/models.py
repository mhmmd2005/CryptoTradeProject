from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import User


class DollarWallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="crypto_wallets")
    address = models.CharField(max_length=200)
    private_key = models.CharField(max_length=500)

    # 🌟 کالیبره شدن اعشار به 6 جهت همگام‌سازی با سایر مدل‌ها و جلوگیری از خطای دیتابیس
    balance = models.DecimalField(decimal_places=6, max_digits=20, default=Decimal('0.000000'))
    frozen_balance = models.DecimalField(decimal_places=6, max_digits=20, default=Decimal('0.000000'))
    currency = models.CharField(max_length=20, default="usdttrc20")

    class Meta:
        verbose_name = "Crypto Wallet"
        verbose_name_plural = "Crypto Wallets"
        unique_together = ('user', 'currency')
        ordering = ['currency']

    def __str__(self):
        return f"{self.user.username} | {self.currency.upper()} | Bal: {self.balance}"

    @property
    def total_assets(self):
        return self.balance + self.frozen_balance

    @property
    def currency_upper(self):
        if self.currency == 'usdttrc20': return 'USDT'
        return self.currency.upper()

    @property
    def network_name(self):
        if self.currency in ['usdttrc20', 'trx']:
            return 'TRC-20'
        elif self.currency == 'eth':
            return 'ERC-20'
        elif self.currency == 'btc':
            return 'Native'
        return 'Crypto'


class CurrencyConfig(models.Model):
    CURRENCY_CHOICES = [
        ('usdttrc20', 'USDT (TRC-20)'),
        ('btc', 'Bitcoin'),
        ('eth', 'Ethereum'),
        ('trx', 'Tron'),
    ]
    code = models.CharField(max_length=20, choices=CURRENCY_CHOICES, unique=True, verbose_name="کد ارز")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    allow_auto_withdraw = models.BooleanField(default=True, verbose_name="اجازه برداشت خودکار")
    auto_withdraw_limit = models.DecimalField(max_digits=20, decimal_places=6, verbose_name="سقف واریز خودکار")
    admin_review_limit = models.DecimalField(max_digits=20, decimal_places=6, verbose_name="سقف بررسی امنیتی ادمین")
    fee_structure = models.JSONField(default=dict, verbose_name="ساختار کارمزد (JSON)")

    def __str__(self):
        return f"{self.code.upper()} Configuration"

    def get_fee(self, amount):
        """محاسبه هوشمند کارمزد با پشتیبانی از مقادیر اعشاری"""
        fees = self.fee_structure
        # تبدیل مقدار درخواستی به Decimal برای مقایسه دقیق
        amount_dec = Decimal(str(amount))

        # استخراج و مرتب‌سازی کلیدهای غیر از "default"
        tiers = []
        for k in fees.keys():
            if k != "default":
                try:
                    tiers.append(Decimal(k))
                except:
                    continue  # نادیده گرفتن کلیدهای نامعتبر

        sorted_tiers = sorted(tiers)

        # منطق مقایسه
        for tier in sorted_tiers:
            if amount_dec <= tier:
                return Decimal(str(fees[str(tier)]))

        # اگر در پله‌ها نبود، بازگشت به default
        return Decimal(str(fees.get("default", "10.0")))

    def clean(self):
        from django.core.exceptions import ValidationError

        if not isinstance(self.fee_structure, dict):
            raise ValidationError("The fee structure format must be a valid JSON.")

        for key, value in self.fee_structure.items():
            # Validate Key (Tiers)
            if key != 'default':
                try:
                    Decimal(key)
                except:
                    raise ValidationError(f"The key '{key}' must be a valid number.")

            # Validate Value (Fee Amount)
            try:
                Decimal(str(value))
            except:
                raise ValidationError(f"The fee value for '{key}' must be a valid number.")


class WithdrawRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Done'),
    ]
    wallet = models.ForeignKey(DollarWallet, on_delete=models.CASCADE, related_name='withdraw_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_withdrawals', null=True)
    amount = models.DecimalField(max_digits=20, decimal_places=6)
    target_address = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confirmed = models.BooleanField(default=False)
    tx_hash = models.CharField(max_length=200, null=True, blank=True)
    fee = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    processed_by = models.ForeignKey('adminPanel.AdminUser', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='processed_withdrawals')
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_amount(self):
        return self.amount + self.fee


class WalletTransaction(models.Model):
    TRANSACTION_TYPE = (('deposit', 'Deposit'), ('withdraw', 'Withdraw'))
    TRANSACTION_STATUS = (('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed'))

    wallet = models.ForeignKey(DollarWallet, on_delete=models.CASCADE, related_name="transactions")
    withdraw = models.ForeignKey(WithdrawRequest, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='transactions')
    tx_hash = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=20, decimal_places=6)
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPE)
    confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=TRANSACTION_STATUS, default='pending')

    payment_id = models.CharField(max_length=100, unique=True)
    purchase_id = models.CharField(max_length=100, unique=True)
    pay_address = models.CharField(max_length=200)

    timestamp = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    user_message = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-timestamp']
