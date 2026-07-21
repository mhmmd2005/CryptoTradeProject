from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_email_task(subject, message, recipient_list):
    """
    Sends an email asynchronously.
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        return f"Email successfully sent to {recipient_list}."
    except Exception as e:
        return f"Error sending email: {str(e)}"
