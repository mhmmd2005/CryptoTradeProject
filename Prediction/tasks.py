import logging

logger = logging.getLogger(__name__)
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from celery import shared_task
from redis.exceptions import LockError  # برای مدیریت قفل هم‌پوشانی  # فرضی بر اساس متغیرها
from .services import get_historical_price  # یا هر مسیری که تابع قیمت در آن است

logger = logging.getLogger(__name__)
from Prediction.models import WalletJournal
from adminPanel.models import PlatformRevenue
from constants import TRADING_ENTRY_WINDOW
from wallet.models import DollarWallet
from .models import Prediction
from .models import PredictionRound
from .utils import get_live_price

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# 1) Activate pending rounds
# ---------------------------------------------------------------------
@shared_task
def activate_pending_rounds():
    now = timezone.now()
    # فقط راندهایی که زمان شروعشان رسیده یا گذشته است
    rounds = PredictionRound.objects.filter(status="pending", start_at__lte=now)

    for r in rounds:
        # 🛡️ استعلام قیمت زنده قبل از فعال‌سازی
        live_price = get_live_price(r.asset.symbol)

        if not live_price or live_price <= 0:
            # اگر قیمت در دسترس نبود، از این راند عبور کن و خطا را لاگ کن
            logger.error(f"Failed to activate Round {r.id}: Price for {r.asset.symbol} is unavailable.")
            continue

            # اگر قیمت موجود بود، راند را فعال کن
        r.status = "active"
        r.current_tf = 1
        r.current_tf_start_at = now
        r.price_open = live_price  # ذخیره قیمت واقعی بایننس

        r.save(update_fields=[
            "status",
            "current_tf",
            "current_tf_start_at",
            "price_open"
        ])

        logger.info(f"Successfully activated Round {r.id} for {r.asset.symbol} at ${live_price}")

        # زمان‌بندی برای سیکل بعدی (TF Advance)
        advance_timeframe.apply_async(
            args=[r.id],
            eta=now + timedelta(seconds=r.timeframe_seconds)
        )


# ---------------------------------------------------------------------
# 2) Advance TF (INFINITE until admin cancels)
# ---------------------------------------------------------------------

@shared_task(bind=True, max_retries=3)
def advance_timeframe(self, round_id):
    cache_key = f"round:{round_id}:tf_lock"
    if cache.get(cache_key):
        return
    cache.set(cache_key, 1, timeout=2)

    try:
        with transaction.atomic():
            r = PredictionRound.objects.select_for_update().get(id=round_id)

            if r.status != "active":
                return

            # --- تغییر به 20 ثانیه (از طریق متغیر ثابت) ---
            TOTAL_CYCLE = r.timeframe_seconds + TRADING_ENTRY_WINDOW

            new_start = r.current_tf_start_at + timedelta(seconds=TOTAL_CYCLE)

            r.current_tf += 1
            r.current_tf_start_at = new_start
            r.save(update_fields=["current_tf", "current_tf_start_at"])

            # زمان اجرای بعدی (ETA) دقیقاً سیکل بعدی
            next_eta = new_start + timedelta(seconds=r.timeframe_seconds)

        # 📡 اطلاع‌رسانی به فرانت‌اند
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            "round_updates",
            {
                "type": "round_update",
                "status": "tf_advanced",
                "round_id": r.id,
                "asset": r.asset.symbol,
                "tf_number": r.current_tf,
                "next_tf_ends_at": next_eta.isoformat(),
            }
        )

        # 🔁 زمان‌بندی خودکار سیکل بعدی
        advance_timeframe.apply_async(
            args=[r.id],
            eta=next_eta
        )

    except PredictionRound.DoesNotExist:
        logger.warning(f"Round {round_id} not found")


@shared_task
def advance_timeframe_auto():
    from django.utils import timezone
    from .models import PredictionRound

    now = timezone.now()

    rounds = PredictionRound.objects.filter(status="active")

    for r in rounds:
        tf_end = r.current_tf_start_at + timedelta(seconds=r.timeframe_seconds)

        if now >= tf_end:
            advance_timeframe.delay(r.id)


@shared_task(ignore_result=True)
def send_ws_notification(user_id, event_data):
    """تسک اختصاصی و سبک برای ارسال پیام وب‌ساکت بدون درگیر کردن دیتابیس"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f"user_updates_{user_id}",
            event_data
        )
    except Exception as ws_err:
        logger.error(f"WebSocket notification failed for user {user_id}: {ws_err}")


@shared_task
def settle_expired_predictions():
    lock_key = "lock:settle_expired_predictions"

    try:
        # 🛡️ blocking_timeout=0 یعنی اگر تسک قبلی هنوز قفل را در دست دارد، منتظر نمان و فوراً اکسپشن بده
        with cache.lock(lock_key, timeout=15, blocking_timeout=0):
            now = timezone.now()
            expired_preds = Prediction.objects.filter(
                settled=False,
                expected_payout_at__lte=now
            ).select_related('user', 'round__asset', 'round')

            if not expired_preds.exists():
                return

            for pred in expired_preds:
                symbol = pred.round.asset.symbol
                exact_close_time = pred.expected_payout_at

                # دریافت قیمت قطعی راس ثانیه پایان کاندل
                exit_price = get_historical_price(symbol, exact_close_time)

                if not exit_price:
                    logger.warning(f"Price for {symbol} at {exact_close_time} not ready yet. Skipping for next tick.")
                    continue

                entry_price = pred.price_at_entry
                fee_percent = Decimal(str(pred.round.admin_fee_percent))

                if exit_price == entry_price:
                    process_payout(pred.id, pred.amount, Decimal("0"), "refund", exit_price)
                else:
                    is_win = (pred.direction == "up" and exit_price > entry_price) or \
                             (pred.direction == "down" and exit_price < entry_price)

                    if is_win:
                        gross_payout = pred.amount * Decimal("1.95")
                        net_profit = gross_payout - pred.amount
                        admin_commission = (net_profit * (fee_percent / Decimal("100"))).quantize(Decimal("0.00"))
                        final_payout = gross_payout - admin_commission
                        process_payout(pred.id, final_payout, admin_commission, "win", exit_price)
                    else:
                        process_payout(pred.id, Decimal("0"), Decimal("0"), "lose", exit_price)

    except LockError:
        # 💡 این یعنی تسک قبلی هنوز دارد داده‌ها را پردازش می‌کند؛ پس این ثانیه را نادیده می‌گیریم تا تداخلی ایجاد نشود.
        logger.debug("Settle task is already running in another worker. Skipping this tick.")
        return


def process_payout(prediction_id, user_amount, admin_fee, result_status, exit_price):
    try:
        with transaction.atomic():
            pred = Prediction.objects.select_for_update().get(id=prediction_id)
            if pred.settled:
                return

            # ۱. اصلاح عملیات کیف پول (فراخوانی مستقیم از مدل بجای ریلیشن)
            if user_amount > 0:
                # اینجا با فیلتر کردن، هم ارور Attribute را حل کردیم هم محدودیت ارزی را اعمال کردیم
                wallet = DollarWallet.objects.select_for_update().get(
                    user=pred.user,
                    currency='usdttrc20'
                )

                old_balance = wallet.balance
                wallet.balance += user_amount
                wallet.save(update_fields=["balance"])

                WalletJournal.objects.create(
                    user=pred.user, amount=user_amount, balance_before=old_balance,
                    balance_after=wallet.balance, reference_id=f"Pred_{pred.id}",
                    action_type='payout_win' if result_status == "win" else 'refund',
                    prediction_id=pred.id, is_win=(result_status == "win"),
                    fee_deducted=admin_fee, description=f"Settlement: {result_status} | Fee: {admin_fee}$"
                )

            # ۲. عملیات درآمد پلتفرم (بدون تغییر)
            if admin_fee > 0:
                revenue_acc = PlatformRevenue.get_revenue_account()
                revenue = PlatformRevenue.objects.select_for_update().get(id=revenue_acc.id)
                revenue.balance += admin_fee
                revenue.save(update_fields=["balance"])

            # ۳. تسویه نهایی
            pred.settle_prediction(
                final_result=result_status,
                payout_amount=user_amount,
                close_price=exit_price,
                fee=admin_fee
            )

        # ۳. ارسال ناهمگام به وب‌ساکت (بیرون از بلاک اتمیک)
        entry_price = Decimal(str(pred.price_at_entry))
        close_price = Decimal(str(exit_price))
        price_diff = close_price - entry_price

        event_data = {
            "type": "settlement_notification",
            "prediction_id": pred.id,
            "symbol": pred.symbol_saved,
            "direction": pred.direction,
            "timeframe": pred.timeframe_seconds,
            "entry_price": str(pred.price_at_entry),
            "exit_price": str(exit_price),
            "price_difference": str(price_diff),
            "result": result_status,
            "payout": str(user_amount),
            "amount": str(pred.amount),
            "settled_at": timezone.now().isoformat()
        }

        send_ws_notification.delay(pred.user.id, event_data)

    except Exception as e:
        logger.error(f"Critical error in process_payout for Pred {prediction_id}: {str(e)}")
