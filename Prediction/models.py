# prediction/models.py
from datetime import timedelta
from decimal import Decimal, getcontext

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from constants import TRADING_ENTRY_WINDOW

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
    # ⏱ Infinite Timeframe (ثابت، تکرارشونده)
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
            MinValueValidator(Decimal("1.00")),  # حداقل 1 درصد
            MaxValueValidator(Decimal("5.00"))  # حداکثر 5 درصد
        ],
        help_text="Admin commission fee between 1% and 5%"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-start_at",)

    def __str__(self):
        return f"{self.asset.symbol} Round {self.id}"

    # --------------------------------------------------
    @property
    def all_timeframes(self):
        """Return all defined TFs with their remaining time"""
        tf_seconds = [
            self.tf1_seconds,
            self.tf2_seconds,
            self.tf3_seconds,
            self.tf4_seconds,
        ]
        now = timezone.now()
        tfs = []
        start_at = self.current_tf_start_at
        for i, sec in enumerate(tf_seconds, start=1):
            if sec > 0:
                end = start_at + timedelta(seconds=sec)
                remaining = max(0, int((end - now).total_seconds()))
                tfs.append({
                    "index": i,
                    "seconds": sec,
                    "remaining": remaining,
                    "active": (i == self.current_tf),
                })
        return tfs

    def get_current_cycle(self):
        now = timezone.now()
        total_cycle = self.timeframe_seconds + TRADING_ENTRY_WINDOW
        return int((now - self.current_tf_start_at).total_seconds() // total_cycle)

    # --------------------------------------------------
    # ⏳ باقی‌مانده‌ی TF فعلی
    # --------------------------------------------------
    @property
    def remaining_seconds(self):
        end = self.current_tf_start_at + timedelta(seconds=self.timeframe_seconds)
        return max(0, int((end - timezone.now()).total_seconds()))

    # --------------------------------------------------
    # 📦 خروجی برای فرانت (فقط TF فعال)
    # --------------------------------------------------
    def to_dict_for_frontend(self):
        end_at = self.current_tf_start_at + timedelta(seconds=self.timeframe_seconds)

        return {
            "id": self.id,
            "status": self.status,
            "current_tf": self.current_tf,
            "timeframe_seconds": self.timeframe_seconds,
            "remaining_seconds": self.remaining_seconds,
            "current_tf_start_at": self.current_tf_start_at.isoformat(),
            "current_tf_ends_at": end_at.isoformat(),
            "start_at": self.start_at.isoformat() if self.start_at else None,
        }

    # --------------------------------------------------
    @property
    def is_active(self):
        return self.status == "active"

    # --------------------------------------------------
    # 📊 Stakes
    # --------------------------------------------------
    @property
    def total_stake_up(self):
        return self.predictions.filter(direction="up").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")

    @property
    def total_stake_down(self):
        return self.predictions.filter(direction="down").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")

    @property
    def total_stake(self):
        return self.total_stake_up + self.total_stake_down

    # --------------------------------------------------
    # 🔒 بستن راند (توسط ادمین)
    # --------------------------------------------------
    def close_round(self, price_close: Decimal):
        self.price_close = price_close
        self.status = "closed"
        self.save(update_fields=["price_close", "status"])

    def cancel_round(self):
        if self.price_close is None:
            self.price_close = self.price_open
        self.status = "cancelled"
        self.settled_at = timezone.now()
        self.save(update_fields=["status", "settled_at", "price_close"])


class Prediction(models.Model):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ذخیره مقدار اولیه پایگاه‌داده برای بررسی تغییرات غیرمجاز
        self._original_payout = self.payout
        self._original_result = self.result
        self._allow_settlement = False

    def clean(self):
        # ولیدیشن‌های مربوط به سقف و کف سفارش
        if self.round:
            if self.round.min_bet_amount is not None and self.amount < self.round.min_bet_amount:
                raise ValidationError({"amount": f"حداقل مبلغ مجاز {self.round.min_bet_amount}$ است"})
            if self.round.max_bet_amount is not None and self.amount > self.round.max_bet_amount:
                raise ValidationError({"amount": f"حداکثر مبلغ مجاز {self.round.max_bet_amount}$ است"})

    def settle_prediction(self, final_result, payout_amount, close_price, fee=Decimal("0.00")):
        """
        🎯 متد مرکزی و انحصاری برای تسویه تریدها.
        فقط فرآیندهای پس‌زمینه (Celery/Worker) مجاز به فراخوانی این متد هستند.
        """
        self._allow_settlement = True
        self.result = final_result
        self.payout = Decimal(str(payout_amount))
        self.price_at_close = close_price
        self.fee_amount = Decimal(str(fee))
        self.settled = True
        self.save()

    def save(self, *args, **kwargs):
        # ۱. حفاظت از لایه فیلد مالی (Payout Protection Shield)
        if self.pk:
            if (
                    self.payout != self._original_payout or self.result != self._original_result) and not self._allow_settlement:
                raise ValidationError(
                    "تغییر مستقیم فیلد Payout یا Result غیرمجاز است. از متد settle_prediction استفاده کنید.")

        # ۲. حفظ تاریخچه سمبل
        if not self.symbol_saved and self.round and self.round.asset:
            self.symbol_saved = self.round.asset.symbol

        # ۳. منطق محاسباتی زمان‌بندی چرخه‌ها
        if not self.id and self.round:
            start_at = self.round.current_tf_start_at
            now = timezone.now()
            elapsed = (now - start_at).total_seconds()
            ENTRY_WINDOW = 20
            total_cycle = self.timeframe_seconds + ENTRY_WINDOW

            if self.timeframe_index is None:
                self.timeframe_index = int(max(0, elapsed) // total_cycle)

            if not self.expected_payout_at:
                cycle_start = start_at + timedelta(seconds=self.timeframe_index * total_cycle)
                trade_start = cycle_start + timedelta(seconds=ENTRY_WINDOW)
                self.expected_payout_at = trade_start + timedelta(seconds=self.timeframe_seconds)

        super().save(*args, **kwargs)

        # به‌روزرسانی مقادیر اصلی پس از ذخیره‌سازی موفق
        self._original_payout = self.payout
        self._original_result = self.result
        self._allow_settlement = False


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
    prediction_id = models.IntegerField(null=True, blank=True)  # برای ردیابی راحت‌تر
    entry_price = models.DecimalField(max_digits=30, decimal_places=10, null=True, blank=True)
    fee_deducted = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    description = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ('-created_at',)

    # داخل کلاس WalletJournal در models.py
    def get_admin_profit(self):
        if self.action_type == 'payout_win':
            return f"{self.fee_deducted}$"
        return "-"

    get_admin_profit.short_description = "Admin Profit"
