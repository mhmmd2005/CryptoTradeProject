from django.urls import path

from .views import UserAddTicketView, MyTicketView, delete_ticket, ticket_detail, AllNotifications, \
    ArchiveNotificationsView, FAQView, update_email_settings, BannedPageView, CreateSupportTicketView

urlpatterns = [
    path('support/add-ticket/', UserAddTicketView.as_view(), name='add-ticket'),
    path('support/my-ticket/', MyTicketView.as_view(), name='my-ticket'),

    path('ticket/delete/<int:pk>/', delete_ticket, name='delete-ticket'),
    path('ticket/detail/<int:ticket_id>/', ticket_detail, name='ticket_detail'),
    path('Notifications', AllNotifications.as_view(), name='all_notifications'),
    path('FAQ', FAQView.as_view(), name='faq'),
    path('notifications/archive/', ArchiveNotificationsView.as_view(), name='archive-notifications'),
    path('update-email-settings/', update_email_settings, name='update_email_settings'),

    path('banned/', BannedPageView.as_view(), name='banned_page'),
    path('create-support-ticket/', CreateSupportTicketView.as_view(), name='create_support_ticket'),
]
