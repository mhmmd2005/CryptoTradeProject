from decimal import Decimal

from django.db import models
from django.urls import reverse, NoReverseMatch
from accounts.models import User


class DollarWallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="crypto_wallets")
    address = models.CharField(max_length=200)
    private_key = models.CharField(max_length=500)
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

    def get_absolute_url(self):
        return reverse('buy-and-sell')


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

    def get_absolute_url(self):
        return reverse('withdraw-transaction-list')


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

    class Meta:
        ordering = ['-timestamp']

    def get_absolute_url(self):
        if self.type == 'deposit':
            return reverse('deposit-transaction-list')
        elif self.type == 'withdraw':
            return reverse('withdraw-transaction-list')
        return reverse('latest_transactions')
