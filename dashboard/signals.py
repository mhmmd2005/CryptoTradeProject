from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from UserPanel.models import UserTicket
from adminPanel.models import TicketReply, AdminUser
from .models import Notification


@receiver(post_save, sender=UserTicket)
def notify_admins_on_new_ticket(sender, instance, created, **kwargs):
    if created:
        try:
            support_admins = AdminUser.objects.all()
            target_link = reverse('admin_ticket_detail', args=[instance.id])

            for admin in support_admins:
                Notification.objects.create(
                    admin_recipient=admin,
                    title="New Ticket Submitted",
                    message=f"User {instance.user.username} created a new ticket: {instance.title}",
                    category='ticket',  # دسته‌بندی برای ادمین
                    notification_type="message",
                    link=target_link
                )
        except Exception as e:
            print(f"JARVIS SIGNAL ERROR: {e}")


@receiver(post_save, sender=TicketReply)
def notify_user_on_admin_reply(sender, instance, created, **kwargs):
    if created:
        try:
            Notification.objects.create(
                user=instance.ticket.user,
                title="Ticket Replied",
                message=f"Support team has replied to your ticket: '{instance.ticket.title}'",
                category="ticket",  # دسته‌بندی برای کاربر
                notification_type="message",
                link=reverse('ticket_detail', args=[instance.ticket.id])
            )
        except Exception as e:
            print(f"JARVIS REPLY SIGNAL ERROR: {e}")
