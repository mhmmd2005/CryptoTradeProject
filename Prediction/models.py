# prediction/models.py
from decimal import Decimal, getcontext

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

User = settings.AUTH_USER_MODEL
getcontext().prec = 28

DIRECTION_CHOICES = (("up", "UP"), ("down", "DOWN"))
RESULT_CHOICES = (("pending", "Pending"), ("win", "Win"), ("lose", "Lose"), ("tie", "Tie"),
                  ("refunded", "Refunded"))


class Asset(models.Model):
    symbol = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=64, blank=True)
    min_bet_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("10.00"))
    timeframes = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.symbol

    def get_absolute_url(self):
        return reverse('dashboard:prediction', kwargs={'symbol': self.symbol})


class PredictionRound(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("active", "Active"),
        ("cancelled", "Cancelled"),
        ("closed", "Closed"),
        ("settled", "Settled"),
    )

    asset = models.ForeignKey("Asset", on_delete=models.CASCADE, related_name="rounds")
    title = models.CharField(max_length=128, blank=True)

    start_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")

    tf1_seconds = models.PositiveIntegerField(help_text="Timeframe 1 (seconds)", default=0)
    tf2_seconds = models.PositiveIntegerField(help_text="Timeframe 2 (seconds)", default=0)
    tf3_seconds = models.PositiveIntegerField(help_text="Timeframe 3 (seconds)", default=0)
    tf4_seconds = models.PositiveIntegerField(help_text="Timeframe 4 (seconds)", default=0)
    timeframe_seconds = models.PositiveIntegerField(help_text="مدت هر تایم‌فریم (ثانیه)")
    current_tf = models.PositiveIntegerField(default=1)
    current_tf_start_at = models.DateTimeField()

    sequence_number = models.PositiveIntegerField(default=1)

    min_bet_amount = models.DecimalField(max_digits=20, decimal_places=2)
    max_bet_amount = models.DecimalField(max_digits=20, decimal_places=2)

    price_open = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)
    price_close = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)

    admin_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.00"),
        validators=[
            MinValueValidator(Decimal("1.00")),
            MaxValueValidator(Decimal("5.00"))
        ],
        help_text="Admin commission fee between 1% and 5%"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-start_at",)

    def __str__(self):
        return f"{self.asset.symbol} Round {self.id}"

    def get_absolute_url(self):
        if self.asset and self.asset.symbol:
            return reverse('dashboard:prediction', kwargs={'symbol': self.asset.symbol})
        return reverse('dashboard:prediction-default')


class Prediction(models.Model):
    DIRECTION_CHOICES = (("up", "Up"), ("down", "Down"))
    RESULT_CHOICES = (("pending", "Pending"), ("win", "Win"), ("loss", "Loss"), ("refund", "Refund"))

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="predictions")
    round = models.ForeignKey("PredictionRound", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="predictions")
    card_index = models.PositiveIntegerField(default=1)
    timeframe_seconds = models.PositiveIntegerField(default=60)
    timeframe_index = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    price_at_entry = models.DecimalField(max_digits=30, decimal_places=10, null=True)
    price_at_close = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expected_payout_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, default="pending", db_index=True)
    payout = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    fee_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    settled = models.BooleanField(default=False)
    symbol_saved = models.CharField(max_length=16, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def get_absolute_url(self):
        if self.symbol_saved:
            return reverse('dashboard:prediction', kwargs={'symbol': self.symbol_saved})
        elif self.round and self.round.asset:
            return reverse('dashboard:prediction', kwargs={'symbol': self.round.asset.symbol})
        return reverse('dashboard:prediction-history')


class WalletJournal(models.Model):
    ACTION_CHOICES = (
        ('place_bet', 'Place_bet'),
        ('payout_win', 'Payout_win'),
        ('refund', 'Refund'),
        ('deposit', 'Deposit'),
        ('withdraw', 'Withdraw'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallet_journal")
    amount = models.DecimalField(max_digits=20, decimal_places=2, help_text="مقدار تراکنش (مثبت یا منفی)")
    balance_before = models.DecimalField(max_digits=20, decimal_places=2)
    balance_after = models.DecimalField(max_digits=20, decimal_places=2)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    reference_id = models.CharField(max_length=100, blank=True, null=True, help_text="آی‌دی پیش‌بینی یا تراکنش مرتبط")
    created_at = models.DateTimeField(auto_now_add=True)
    is_win = models.BooleanField(default=False)
    prediction_id = models.IntegerField(null=True, blank=True)
    entry_price = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)
    fee_deducted = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    description = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ('-created_at',)

    def get_absolute_url(self):
        return reverse('dashboard:recent-activity')
