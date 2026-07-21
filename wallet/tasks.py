from celery import shared_task
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import requests
import logging
from django.conf import settings
from wallet.models import WalletTransaction  # ایمپورت مدل برای جلوگیری از NameError

logger = logging.getLogger(__name__)


@shared_task
def check_pending_deposits():
    """
    Automated Task: Checks pending/waiting transactions every 10 seconds.
    Logic: Syncs status with NowPayments API and updates user balance atomically.
    """
    now = timezone.now()
    # Logic preserved: Targeting only active/pending transactions
    pending_txs = WalletTransaction.objects.filter(status__in=['pending', 'waiting'])

    for tx in pending_txs:
        try:
            # 🕒 Expiration Check
            if tx.expires_at and now > tx.expires_at:
                if tx.status != 'failed':
                    tx.status = 'failed'
                    tx.user_message = "❌ Payment time has expired."
                    tx.save(update_fields=['status', 'user_message'])
                logger.info(f"[Expired] Transaction {tx.id} - Time limit reached.")
                continue

            # 🔄 Status Synchronization
            if tx.status == 'waiting':
                tx.status = 'pending'
                tx.save(update_fields=['status'])

            # 📡 NowPayments API Integration
            url = f'https://api.nowpayments.io/v1/payment/{tx.payment_id}'
            headers = {'x-api-key': settings.NOW_PAYMENT_API_KEY}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Check for HTTP errors
            data = response.json()

            status = data.get('payment_status')
            price_amount = data.get('price_amount')

            # ✅ SUCCESS: Atomic Balance Update
            if status == 'finished':
                paid_amount = Decimal(str(price_amount)) if price_amount else tx.amount
                with transaction.atomic():
                    # Refreshing the transaction from DB to prevent stale data
                    current_tx = WalletTransaction.objects.select_for_update().get(id=tx.id)
                    if current_tx.status != 'success':
                        current_tx.status = 'success'
                        current_tx.confirmed = True
                        current_tx.amount = paid_amount
                        current_tx.user_message = "✅ Deposit successful! Funds added to your wallet."
                        current_tx.save(update_fields=['status', 'confirmed', 'amount', 'user_message'])

                        wallet = current_tx.wallet
                        wallet.balance += paid_amount
                        wallet.save(update_fields=['balance'])
                        logger.info(f"[Success] Wallet {wallet.id} credited with {paid_amount}")

            # ❌ FAILED/EXPIRED
            elif status in ['failed', 'expired']:
                tx.status = 'failed'
                tx.user_message = f"❌ Transaction {status}."
                tx.save(update_fields=['status', 'user_message'])
                logger.warning(f"[Failed] Transaction {tx.id} marked as {status}")

            # ⏳ STILL PROCESSING
            elif status in ['waiting', 'confirming', 'pending']:
                tx.user_message = "⏳ Waiting for blockchain confirmation..."
                tx.save(update_fields=['user_message'])

            # 🟠 UNKNOWN STATUS
            else:
                tx.user_message = f"⚠️ Status update: {status}"
                tx.save(update_fields=['user_message', 'status'])

        except requests.RequestException as e:
            logger.error(f"[Network Error] Could not reach NowPayments for tx {tx.id}: {e}")
            # Logic: We don't mark as failed immediately to allow retry in next 10s cycle

        except Exception as e:
            tx.status = 'failed'
            tx.user_message = "⚠️ Internal processing error."
            tx.save(update_fields=['status', 'user_message'])
            logger.critical(f"[System Error] Unexpected failure for tx {tx.id}: {e}")
