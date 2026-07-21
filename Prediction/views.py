import json
import logging
from datetime import timedelta
from decimal import Decimal
from decimal import ROUND_HALF_UP

import pytz
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder  # 💎 الزامی برای فیلدهای Decimal
from django.db import transaction
from django.db.models import Q
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from Prediction.models import WalletJournal
from core.mixins import KYCRequiredMixin, kyc_required_decorator
from wallet.models import DollarWallet
from .models import Asset
from .models import Prediction, PredictionRound
from .utils import get_live_price

logger = logging.getLogger('trading')


# Create your views here.


def format_timeframe_seconds(sec):
    sec = int(sec or 0)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


class PredictionView(LoginRequiredMixin, KYCRequiredMixin, View):
    template_name = "prediction/prediction.html"

    def get(self, request, symbol=None):
        asset = None
        round_obj = None

        # 🌟 اصلاح این خط: واکشی ولت تتر به جای جستجوی اشتباه dollar_wallet
        wallet = None
        if request.user.is_authenticated:
            wallet = request.user.crypto_wallets.filter(currency="usdttrc20").first()

        timeframes = []
        active_bets_json = "[]"

        if symbol:
            asset = get_object_or_404(Asset, symbol=symbol)
            round_obj = asset.rounds.filter(status="active").order_by("-start_at").first()

            if round_obj:
                timeframes = [
                    {"index": tf["index"], "seconds": tf["seconds"], "minutes": tf["seconds"] // 60}
                    for tf in round_obj.all_timeframes
                ]

                if request.user.is_authenticated:
                    active_bets_list = list(Prediction.objects.filter(
                        user=request.user,
                        round=round_obj,
                        settled=False
                    ).values('card_index', 'timeframe_seconds', 'timeframe_index', 'amount'))

                    active_bets_json = json.dumps(active_bets_list, cls=DjangoJSONEncoder)

        context = {
            "wallet": wallet,  # اکنون نمونه ولت واقعی تتر پاس داده می‌شود
            "asset": asset,
            "round": round_obj,
            "timeframes": timeframes,
            "assets": Asset.objects.all(),
            "selected_symbol": symbol,
            "active_bets_json": active_bets_json,
            "server_time": timezone.now().isoformat(),
        }
        return render(request, self.template_name, context)


class PlaceOrderAPI(LoginRequiredMixin, KYCRequiredMixin, View):
    def post(self, request):
        user_id = request.user.id
        logger.info(f"User {user_id} requested a trade.")

        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            logger.error(f"User {user_id} sent invalid JSON.")
            return JsonResponse({"status": "error", "message": "Invalid JSON"})

        bets = data.get("bets", [])
        if not bets:
            return JsonResponse({"status": "error", "message": "No bets provided"})

        COOL_DOWN = 3.5
        validated_bets = []
        total_amount = Decimal("0")
        ENTRY_WINDOW = 20

        for b in bets:
            try:
                amount = Decimal(str(b.get("amount", "0"))).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
                tf_seconds = int(b.get("timeframe", 0))
                card_idx = int(b.get("card_index", 1))
                round_id = b.get("round_id")
                direction = b.get("direction")
            except (ValueError, TypeError):
                continue

            # ۱. چک کردن وضعیت راند
            r = PredictionRound.objects.filter(id=round_id, status="active").first()
            if not r:
                return JsonResponse({"status": "error", "message": "Round not active"})

            # ۲. محاسبات پویای چرخه زمانی (دقیقاً منطبق بر ریاضیات فرانت‌اند)
            now = timezone.now()
            elapsed_total = (now - r.current_tf_start_at).total_seconds()
            TOTAL_CYCLE = tf_seconds + ENTRY_WINDOW

            # 💎 اصلاح حیاتی: محاسبه ایندکس چرخه بر اساس فرمول ریاضی دقیق تایم‌فریم جاری
            current_cycle = int(elapsed_total // TOTAL_CYCLE)
            cycle_elapsed = elapsed_total % TOTAL_CYCLE

            logger.info(f"""
            [ENTRY CHECK DEBUG] User: {user_id}
            Elapsed Total: {elapsed_total}s | Cycle Elapsed: {cycle_elapsed}s
            Current Calculated Cycle: {current_cycle}
            Allowed: {cycle_elapsed <= ENTRY_WINDOW}
            """)

            # بررسی باز بودن پنجره ورود
            is_entry_open = cycle_elapsed < ENTRY_WINDOW
            if not is_entry_open:
                return JsonResponse({"status": "error", "message": "Entry closed"})

            time_left = ENTRY_WINDOW - cycle_elapsed
            if time_left < COOL_DOWN:
                return JsonResponse({
                    "status": "error",
                    "message": f"Market closing soon ({int(time_left)}s)."
                })

            # ۳. جلوگیری از دابل-ترید (🛡️ قفل نفوذناپذیر سمت سرور)
            already_has_bet = Prediction.objects.filter(
                user=request.user,
                round=r,
                card_index=card_idx,
                timeframe_seconds=tf_seconds,
                timeframe_index=current_cycle,  # فیلتر بر اساس چرخه پویا و دقیق
                settled=False
            ).exists()

            if already_has_bet:
                logger.warning(f"User {user_id} attempted double-trade on card {card_idx} for cycle {current_cycle}.")
                return JsonResponse(
                    {"status": "error", "message": "This card is already locked for the current cycle."})

            # ۴. چک کردن محدودیت مبلغ
            if amount < r.min_bet_amount:
                return JsonResponse({"status": "error", "message": f"Min: ${r.min_bet_amount}"})
            if amount > r.max_bet_amount:
                return JsonResponse({"status": "error", "message": f"Max: ${r.max_bet_amount}"})

            # ۵. دریافت قیمت لحظه‌ای
            entry_price = get_live_price(r.asset.symbol)
            if not entry_price:
                return JsonResponse({"status": "error", "message": "Price feed error."})

            validated_bets.append({
                "round": r, "amount": amount, "direction": direction,
                "tf_seconds": tf_seconds, "card_index": card_idx,
                "price": entry_price, "current_cycle": current_cycle
            })
            total_amount += amount

        # ۶. عملیات حساس تراکنش مالی و ثبت ترید (Thread-safe)
        try:
            with transaction.atomic():
                # اصلاح اصلی: فیلتر کردن دقیق بر اساس ارز usdttrc20
                wallet = DollarWallet.objects.select_for_update().filter(
                    user=request.user,
                    currency='usdttrc20'
                ).first()

                if not wallet:
                    logger.error(f"User {user_id} has no usdttrc20 wallet.")
                    return JsonResponse({"status": "error", "message": "USDT-TRC20 wallet not found."})

                # بررسی موجودی
                if wallet.balance < total_amount:
                    logger.warning(
                        f"User {user_id} failed trade: Insufficient balance. Balance: {wallet.balance}, Requested: {total_amount}")
                    return JsonResponse({"status": "error", "message": "Insufficient balance."})

                old_balance = wallet.balance
                wallet.balance -= total_amount
                wallet.save(update_fields=["balance"])

                # ثبت در ژورنال
                WalletJournal.objects.create(
                    user=request.user, amount=-total_amount,
                    balance_before=old_balance, balance_after=wallet.balance,
                    action_type='place_bet', reference_id=f"R_{validated_bets[0]['round'].id}"
                )

                for vb in validated_bets:
                    Prediction.objects.create(
                        user=request.user,
                        round=vb["round"],
                        amount=vb["amount"],
                        direction=vb["direction"],
                        card_index=vb["card_index"],
                        timeframe_seconds=vb["tf_seconds"],
                        timeframe_index=vb["current_cycle"],  # پاس دادن صریح ایندکس به دیتابیس
                        price_at_entry=vb["price"]
                    )

            logger.info(f"User {user_id} trade success. Amount: {total_amount}. New Balance: {wallet.balance}")
            return JsonResponse({"status": "success", "new_balance": f"{wallet.balance:,.2f}"})

        except Exception as e:
            logger.error(f"CRITICAL: Trade execution failed for User {user_id}. Error: {str(e)}", exc_info=True)
            return JsonResponse({"status": "error", "message": "Transaction failed. Please try again."})


class ActiveRoundAPI(LoginRequiredMixin, View):
    def get(self, request, asset_id, timeframe):
        asset = get_object_or_404(Asset, id=asset_id)
        round_obj = asset.rounds.filter(
            timeframe=timeframe,
            status="active"
        ).order_by('-id').first()

        if not round_obj:
            return JsonResponse({"status": "no_round"})

        remaining = int((round_obj.end_at - timezone.now()).total_seconds())
        return JsonResponse({
            "round_id": round_obj.id,
            "sequence": round_obj.sequence_number,
            "timeframe": round_obj.timeframe,
            "start_at": round_obj.start_at,
            "end_at": round_obj.end_at,
            "remaining_seconds": max(0, remaining),
            "price_open": float(round_obj.price_open)
        })


class UserDashboardStatsAPI(LoginRequiredMixin, KYCRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.now().astimezone(pytz.utc).date()

        # ۱. واکشی بهینه تراکنش‌ها
        all_user_preds = Prediction.objects.filter(user=user).select_related('round__asset')
        settled_preds = all_user_preds.filter(settled=True)

        # ۲. محاسبات کلان مالی (Net Profit) - کاملاً امن و مجزا
        global_stats = settled_preds.aggregate(
            total_payout=Sum('payout'),
            total_spent=Sum('amount')
        )
        payout_sum = global_stats['total_payout'] or Decimal('0.00')
        spent_sum = global_stats['total_spent'] or Decimal('0.00')
        net_profit = payout_sum - spent_sum

        # ۳. محاسبه فرمول سود امروز (Today's PnL) - بدون ریسک کرش دیتابیس
        today_stats = settled_preds.filter(created_at__date=today).aggregate(
            today_payout=Sum('payout'),
            today_spent=Sum('amount')
        )
        today_payout_sum = today_stats['today_payout'] or Decimal('0.00')
        today_spent_sum = today_stats['today_spent'] or Decimal('0.00')
        today_profit = today_payout_sum - today_spent_sum

        # ۴. محاسبات نرخ برد (Win Rate)
        total_settled_count = settled_preds.count()
        wins_count = settled_preds.filter(result='win').count()
        losses_count = settled_preds.filter(result='lose').count()
        win_rate = (wins_count / total_settled_count * 100) if total_settled_count > 0 else 0

        # ۵. پیدا کردن بهترین دارایی (Best Asset) - با رفع باگ اردرینگِ Group By
        best_asset_query = settled_preds.order_by().values('symbol_saved').annotate(
            asset_net=Sum('payout') - Sum('amount')
        ).order_by('-asset_net').first()

        best_asset = best_asset_query['symbol_saved'] if (
                best_asset_query and best_asset_query['symbol_saved']) else "N/A"

        # ۶. آماده‌سازی لیست تاریخچه ۱۰ ترید اخیر
        recent_preds = all_user_preds.order_by('-created_at')[:10]
        latest_predictions_data = []

        for p in recent_preds:
            display_symbol = p.symbol_saved or (
                p.round.asset.symbol if p.round and p.round.asset else f"Round #{p.round_id}")
            latest_predictions_data.append({
                "symbol": display_symbol,
                "amount": f"{p.amount:,.2f}",
                "direction": p.direction,
                "entry_price": f"{p.price_at_entry:,.4f}" if p.price_at_entry else "N/A",
                "timeframe": f"{p.timeframe_seconds // 60}m" if p.timeframe_seconds else "1m",
                "result": p.result,
                "payout": f"{p.payout:,.2f}",
                "settled": p.settled,
                "created_at": p.created_at.strftime("%H:%M")
            })

        return JsonResponse({
            "net_profit": f"{net_profit:,.2f}",
            "today_profit": float(today_profit),  # تبدیل به فلوت برای هندلینگ راحت در جاوااسکریپت
            "win_rate": f"{win_rate:.1f}%",
            "wins_count": wins_count,
            "losses_count": losses_count,
            "best_asset": best_asset,
            "total_bets": all_user_preds.count(),
            "latest_predictions": latest_predictions_data
        })


class PredictionHistoryView(LoginRequiredMixin, TemplateView):
    template_name = "prediction/predictions_history.html"

    def get(self, request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            user = request.user
            query = request.GET.get('q', '').strip()
            page_number = request.GET.get('page', 1)

            preds = Prediction.objects.filter(user=user).only(
                'id',
                'created_at',
                'symbol_saved',
                'direction',
                'amount',
                'price_at_entry',
                'price_at_close',
                'settled',
                'result',
                'payout',
                'expected_payout_at',
                'timeframe_seconds'
            ).order_by('-created_at')

            if query:
                preds = preds.filter(
                    Q(symbol_saved__iexact=query) |
                    Q(result__iexact=query) |
                    Q(direction__iexact=query)
                ).distinct()

            paginator = Paginator(preds, 10)
            page_obj = paginator.get_page(page_number)

            data = []
            for p in page_obj:
                display_symbol = p.symbol_saved if p.symbol_saved else "Unknown"

                # 💡 محاسبه امن و بیمه ممیزها برای پایتون فلوت با متد round
                net_profit = 0.0
                if p.settled:
                    if p.result in ['win', 'winner']:
                        net_profit = round(float(p.payout - p.amount), 2)
                    elif p.result in ['lose', 'loss']:
                        net_profit = round(-float(p.amount), 2)

                data.append({
                    "id": p.id,
                    "timestamp": p.created_at.strftime("%Y-%m-%d %H:%M"),
                    "symbol": display_symbol,
                    "direction": p.direction,
                    "amount": float(p.amount),
                    "entry_price": f"{p.price_at_entry:,.4f}" if p.price_at_entry else "N/A",
                    "close_price": f"{p.price_at_close:,.4f}" if p.price_at_close else "Running...",
                    "status": "settled" if p.settled else "pending",
                    "result": p.result,
                    "payout": float(p.payout),
                    "net_profit": net_profit,
                    "payout_time": p.expected_payout_at.strftime("%H:%M:%S") if p.expected_payout_at else "---",
                    "timeframe": f"{p.timeframe_seconds // 60}m",
                })

            return JsonResponse({
                "predictions": data,
                "current_page": page_obj.number,
                "num_pages": paginator.num_pages,
                "total_entries": paginator.count,
                "per_page": 10
            })

        return super().get(request, *args, **kwargs)


@login_required
@kyc_required_decorator
def get_wallet_balance(request):
    # 🌟 واکشی مستقیم ولت تتر (usdttrc20) کاربر از بین تمام ولت‌ها
    wallet = request.user.crypto_wallets.filter(currency="usdttrc20").first()

    if wallet:
        return JsonResponse({
            "status": "success",
            "balance": float(wallet.balance),  # مقدار عددی برای مقایسه در JS
            "formatted_balance": intcomma(f"{wallet.balance:.2f}")
        })

    # اگر به هر دلیلی ولت تتر وجود نداشت، مقدار 0 را برمی‌گردانیم تا قالب خراب نشود
    return JsonResponse({
        "status": "success",
        "balance": 0.0,
        "formatted_balance": "0.00"
    })


@login_required
def next_tf(request):
    prev_tf = int(request.GET.get("prev_tf", 0))
    round_obj = PredictionRound.objects.filter(status="active").last()

    if not round_obj:
        return JsonResponse({})  # اگر راند فعالی نیست

    next_tf_number = round_obj.current_tf
    next_tf_end = (round_obj.current_tf_start_at + timedelta(seconds=round_obj.timeframe_seconds)).isoformat()

    return JsonResponse({
        "next_tf_number": next_tf_number,
        "next_tf_ends_at": next_tf_end,
    })


@login_required
def api_get_active_locks(request):
    symbol = request.GET.get('symbol')

    # واکشی شرط‌های تسویه نشده کاربر
    query = Prediction.objects.filter(user=request.user, settled=False)
    if symbol:
        query = query.filter(round__asset__symbol=symbol)

    # 💎 اصلاح حیاتی: اضافه شدن timeframe_index برای تطبیق چرخه‌ها در فرانت‌اند
    active_bets = list(query.values('card_index', 'timeframe_seconds', 'timeframe_index', 'amount'))
    return JsonResponse({
        "status": "success",
        "active_bets": active_bets
    })


@login_required
def get_cycle_info(start_at, tf_seconds, entry_window):
    now = timezone.now()
    elapsed = (now - start_at).total_seconds()

    total_cycle = tf_seconds + entry_window
    cycle_index = int(max(0, elapsed) // total_cycle)
    cycle_start = r.current_tf_start_at
    cycle_end = cycle_start + timedelta(seconds=TOTAL_CYCLE)

    cycle_elapsed = (now - cycle_start).total_seconds()

    return cycle_index, cycle_elapsed, total_cycle
