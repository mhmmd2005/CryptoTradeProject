import logging
import random
from datetime import timedelta
from decimal import Decimal
import ccxt
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from adminPanel.models import AdminInvitation
from adminPanel.utils import get_platform_liquidity_data

logger = logging.getLogger(__name__)


@shared_task
def send_admin_invitation_email(email, link):
    subject = 'Admin Invitation (Secure System)'
    message = f"""
    Hello,

    You have been invited to join the Administration Panel. Due to security protocols for our financial and prediction systems, this link is only valid for 1 hour.

    Please click the link below to complete your profile and set your credentials:
    {link}

    If you did not expect this invitation, please ignore this email.
    """
    send_mail(subject, message, settings.EMAIL_HOST_USER, [email])


@shared_task
def cleanup_expired_invitations():
    threshold = timezone.now() - timedelta(hours=24)
    deleted_count, _ = AdminInvitation.objects.filter(
        Q(is_used=True) | Q(created_at__lt=threshold)
    ).delete()
    return f"Cleanup successful: {deleted_count} expired/used invitations removed."


@shared_task
def send_admin_edit_otp_task(email, otp_code, target_name):
    subject = 'Verification Code for Admin Account Changes'
    message = (
        f'Dear {target_name},\n\n'
        f'A request has been made to modify your admin account settings.\n'
        f'Your verification code is: {otp_code}\n'
        f'This code will expire in 5 minutes.'
    )
    send_mail(subject, message, settings.EMAIL_HOST_USER, [email])


@shared_task(name="tasks.send_delete_otp")
def send_delete_otp_task(admin_id, email, target_name):
    # ۱. تولید کد ۶ رقمی
    otp = str(random.randint(100000, 999999))

    # ۲. ذخیره در کش (Redis/Cache)
    cache.set(f"delete_otp_{admin_id}", otp, timeout=120)

    # ۳. آماده‌سازی متن پیام
    subject = 'Verification Code for Admin Deletion'
    message = (
        f'Dear Admin,\n\n'
        f'A request has been made to permanently delete the admin account: {target_name}.\n'
        f'Your security verification code is: {otp}\n'
        f'This code is valid for 2 minutes.'
    )

    # ۴. ارسال واقعی ایمیل
    # حالا متغیر email در اینجا شناخته شده است
    send_mail(subject, message, settings.EMAIL_HOST_USER, [email])

    return f"OTP sent to {email}"


@shared_task(name="adminPanel.tasks.send_admin_activation_email")
def send_admin_activation_email(admin_email, login_url):
    subject = 'Access Granted | Admin Panel'
    from_email = settings.DEFAULT_FROM_EMAIL

    # محتوای متنی ساده (برای دستگاه‌های قدیمی)
    text_content = f"Dear Colleague, your admin account has been approved. Login here: {login_url}"

    # محتوای HTML که تایید کردید
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif; background-color: #f4f7f6; padding: 20px; direction: ltr; }}
            .card {{ 
                background-color: #ffffff; 
                border-radius: 8px; 
                padding: 40px; 
                max-width: 500px; 
                margin: 0 auto; 
                box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                text-align: left;
            }}
            .header {{ color: #25a0e2; font-size: 22px; font-weight: 700; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 15px; }}
            .content {{ color: #495057; line-height: 1.8; margin-bottom: 30px; font-size: 15px; }}
            .btn-container {{ text-align: center; margin-top: 10px; }}
            .btn {{ 
                background-color: #00bd9d; 
                color: #ffffff !important; 
                padding: 14px 35px; 
                text-decoration: none; 
                border-radius: 8px; 
                font-weight: 600; 
                display: inline-block;
                box-shadow: 0 4px 6px rgba(0, 189, 157, 0.2);
            }}
            .footer {{ margin-top: 25px; font-size: 12px; color: #adb5bd; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">Access Granted</div>
            <div class="content">
                <p>Dear Colleague,</p>
                <p>We are pleased to inform you that your registration request for the <strong>Admin Panel</strong> has been reviewed and formally <strong>approved</strong> by the Senior Administration.</p>
                <p>Your account is now fully activated. You may access your professional dashboard and begin your operations by clicking the secure link below:</p>
            </div>
            <div class="btn-container">
                <a href="{login_url}" class="btn">Click Here</a>
            </div>
            <div class="content" style="margin-top: 30px; font-size: 13px; border-top: 1px solid #f8f9fa; padding-top: 15px;">
                <p>Welcome to the management team. We look forward to your contributions to the platform.</p>
            </div>
        </div>
        <div class="footer">
            Security Notice: This is an automated message from the CryptoTrade system. Please do not reply to this address.
        </div>
    </body>
    </html>
    """

    msg = EmailMultiAlternatives(subject, text_content, from_email, [admin_email])
    msg.attach_alternative(html_content, "text/html")

    try:
        msg.send()
        return f"Email successfully sent to {admin_email}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"


def sanitize_data(data):
    """تبدیل تمام آبجکت‌های Decimal به String برای جلوگیری از خطاهای سریال‌سازی در ردیس"""
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(v) for v in data]
    elif isinstance(data, Decimal):
        return str(data)
    return data


@shared_task(name="nex_trade_fetch_live_prices")
def nex_trade_fetch_live_prices():
    try:
        exchange = ccxt.binance()
        symbols = ['BTC/USDT', 'ETH/USDT', 'TRX/USDT']

        # ۱. دریافت تمام دیتا در یک درخواست (Batch Request) - کاهش بار شبکه
        tickers = exchange.fetch_tickers(symbols)
        real_data = {}

        for symbol in symbols:
            ticker = tickers.get(symbol)
            if ticker:
                code = symbol.split('/')[0].lower()
                real_data[code] = {
                    'price': Decimal(str(ticker['last'])),
                    'change_pct': Decimal(str(ticker['percentage']))
                }

        # ۲. پیاده‌سازی استراتژی ذخیره‌سازی لایه‌ای (Last-Known-Good)
        if real_data:
            clean_prices = sanitize_data(real_data)

            # لایه اول: کش کوتاه‌مدت ۵ دقیقه‌ای (هر ۳۰ ثانیه نوسازی می‌شود)
            cache.set('nex_trade_live_prices', clean_prices, timeout=300)

            # لایه دوم: کش بلندمدت ۲۴ ساعته (سپر بلای سیستم در زمان قطعی بایننس یا شبکه سرور)
            cache.set('nex_trade_last_known_prices', clean_prices, timeout=86400)

            # تریگر کردنِ پخشِ زنده روی وب‌سوکت
            broadcast_live_liquidity.delay()
            return "Market data synced successfully (Batch Mode)."

        return "No data received from exchange."

    except Exception as e:
        logger.error(f"Error in Batch Fetch: {e}")
        return f"Failed to fetch market data: {str(e)}"


@shared_task(name="adminPanel.tasks.broadcast_live_liquidity")
def broadcast_live_liquidity():
    assets_data = get_platform_liquidity_data()
    clean_data = sanitize_data(assets_data)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "admin_liquidity_group",
        {
            "type": "broadcast_liquidity",
            "assets": clean_data
        }
    )
    return "Liquidity broadcast stream sent via Redis channel layer."
