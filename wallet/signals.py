import logging
from decimal import Decimal

from cryptography.fernet import Fernet
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from tronpy import Tron

from accounts.models import User
from wallet.models import DollarWallet
from wallet.models import WithdrawRequest

logger = logging.getLogger(__name__)


def get_or_create_wallet_safely(user, currency):
    """
    هسته مرکزی و لایه دفاعی ساخت و واکشی ولت‌ها.
    اگر ولت وجود نداشته باشد، آن را به صورت آنی و امن همراه با آدرس خلق می‌کند.
    """
    currency = currency.lower()

    # ۱. بررسی وجود ولت از قبل
    wallet = user.crypto_wallets.filter(currency=currency).first()
    if wallet:
        return wallet

    # ۲. اگر ولت وجود نداشت، در لحظه ساخته می‌شود (Lazy Creation)
    fernet = Fernet(settings.FERNET_KEY.encode())
    address = ""
    encrypted_key = ""

    if currency in ['usdttrc20', 'trx']:
        # بررسی اینکه آیا یکی از این دو ارز شبکه ترون از قبل آدرس دارد یا خیر (اشتراک آدرس)
        shared_wallet = user.crypto_wallets.filter(currency__in=['usdttrc20', 'trx']).first()
        if shared_wallet:
            address = shared_wallet.address
            encrypted_key = shared_wallet.private_key
        else:
            client = Tron()
            tron_account = client.generate_address()
            address = tron_account['base58check_address']
            encrypted_key = fernet.encrypt(tron_account['private_key'].encode()).decode()

    elif currency == 'eth':
        from eth_account import Account
        eth_account = Account.create()
        address = eth_account.address
        encrypted_key = fernet.encrypt(eth_account.key.hex().encode()).decode()

    elif currency == 'btc':
        from bitcoinlib.keys import Key
        btc_key = Key()
        address = btc_key.address()
        # 🛠️ اصلاح متد استاندارد btc
        btc_private_wif = btc_key.wif()
        encrypted_key = fernet.encrypt(btc_private_wif.encode()).decode()
    else:
        raise ValueError(f"Unsupported currency: {currency}")

    return DollarWallet.objects.create(
        user=user,
        currency=currency,
        address=address,
        private_key=encrypted_key,
        balance=Decimal('0.00'),
        frozen_balance=Decimal('0.00')
    )


@receiver(post_save, sender=User)
def create_user_multi_currency_wallets(sender, instance, created, **kwargs):
    """
    ساخت خودکار تمام ولت‌ها به محض ثبت‌نام کاربر جدید
    """
    if created:
        supported_currencies = ['usdttrc20', 'trx', 'eth', 'btc']
        for currency in supported_currencies:
            try:
                get_or_create_wallet_safely(instance, currency)
            except Exception as e:
                logger.error(f"Failed to auto-create {currency} wallet for {instance.email}: {str(e)}")


@receiver(post_save, sender=WithdrawRequest)
def sync_tx_hash_to_transaction(sender, instance, **kwargs):
    """
    همگام‌سازی هش تراکنش بلاکچین از درخواست برداشت به تراکنش‌های مرتبط.
    """
    # 🌟 کالیبره شد: استفاده از فیلد واقعی tx_hash به جای فیلد ناموجود withdraw_tx_hash
    related_transactions = instance.transactions.all()
    if related_transactions.exists() and instance.tx_hash:
        for tx in related_transactions:
            if tx.tx_hash != instance.tx_hash:
                tx.tx_hash = instance.tx_hash
                tx.save(update_fields=['tx_hash'])


@receiver(post_save, sender=WithdrawRequest)
def sync_withdraw_time_to_transaction(sender, instance, created, **kwargs):
    """
    همگام‌سازی زمان پردازش تراکنش به محض تایید یا رد نهایی.
    """
    # 🌟 کالیبره شد: افزودن 'Done' با حروف بزرگ برای هماهنگی کامل با ساختار ویو ادمین
    if instance.status in ['approved', 'done', 'Done', 'rejected'] and instance.processed_at:
        # بروزرسانی بهینه زمان آخرین ویرایش تراکنش‌های مرتبط
        instance.transactions.all().update(updated_at=instance.processed_at)
