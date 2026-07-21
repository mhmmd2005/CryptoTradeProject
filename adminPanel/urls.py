from django.urls import path

# from wallet.views import WalletWithdrawView
from .views import ProfileApproval, ProfileDetailView, ProfileReject, \
    UserWithdrawRequest, AdminWithdrawActionView, AdminLoginView, DeleteProfiles, \
    AdminTicketListView, AdminTicketDetailView, ProfileApprove, AdminLogoutView, AdminLockScreenView, \
    AdminRoundListView, AdminRoundCreateView, AdminRoundUpdateView, round_duration, AdminListView, \
    AdminInviteView, CompleteRegistrationView, AdminDeleteView, AdminUpdateView, AdminLogListView, \
    AdminSecuritySettingsView, PlatformRevenueAPIView, PlatformWithdrawalActionView, AdminRoundDeleteView, \
    AdminRequestManagerView, UserManagementListView, UserDetailView, ToggleUserStatusView, BanUserView, \
    AdminDashboardView, ModifyUserBalanceView

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-panel'),
    path('sign_in/', AdminLoginView.as_view(), name='admin-login'),

    path('Profile-Approval/', ProfileApproval.as_view(), name='profile-approval'),
    path('profile/<int:pk>/', ProfileDetailView.as_view(), name='profile_detail'),
    path('profile/<int:pk>/approve/', ProfileApprove.as_view(), name='profile_approve'),
    path('profile/<int:pk>/reject/', ProfileReject.as_view(), name='profile_reject'),
    path("delete-profiles/", DeleteProfiles.as_view(), name="delete_profiles"),

    path('Withdarw-request/', UserWithdrawRequest.as_view(), name='User-withdraw-request'),
    path('adminPanel/Withdraw-request/<int:withdraw_id>/action/', AdminWithdrawActionView.as_view(),
         name='admin-withdraw-action'),
    path('lock/', AdminLockScreenView.as_view(), name='admin-lock-screen'),

    path('tickets/', AdminTicketListView.as_view(), name='user-ticket_list'),
    path('tickets/<int:ticket_id>/', AdminTicketDetailView.as_view(), name='admin_ticket_detail'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),
    path("rounds/", AdminRoundListView.as_view(), name="admin-round-list"),
    path("rounds/add/", AdminRoundCreateView.as_view(), name="admin-round-create"),
    path("rounds/<int:pk>/edit/", AdminRoundUpdateView.as_view(), name="admin-round-update"),
    path('prediction/round/<int:pk>/delete/', AdminRoundDeleteView.as_view(), name='admin-round-delete'),
    path('ajax/round_duration/<int:round_id>/', round_duration, name='round_duration'),
    path('admins/', AdminListView.as_view(), name='admin-list'),
    path('invite/', AdminInviteView.as_view(), name='admin-invite'),
    path('register/complete/<uuid:token>/', CompleteRegistrationView.as_view(), name='admin-complete-registration'),
    path('delete/<int:admin_id>/', AdminDeleteView.as_view(), name='delete-admin'),
    path('update/<int:pk>/', AdminUpdateView.as_view(), name='update-admin'),
    path('admin-logs/', AdminLogListView.as_view(), name='admin-logs-list'),
    path('security-settings/', AdminSecuritySettingsView.as_view(), name='admin_password'),
    path('api/platform-revenue/', PlatformRevenueAPIView.as_view(), name='platform_revenue_api'),
    # در فایل urls.py
    path('api/withdrawals/process/', PlatformWithdrawalActionView.as_view(), name='withdrawal_action_api_list'),
    path('api/withdrawals/process/<int:pk>/', PlatformWithdrawalActionView.as_view(), name='withdrawal_action_api'),

    path('admins/requests/list/', AdminRequestManagerView.as_view(), name='admin-requests-list'),

    path('admins/requests/action/<int:admin_id>/', AdminRequestManagerView.as_view(), name='admin-request-action'),

    path('user-management/', UserManagementListView.as_view(), name='user-management'),
    path('user-detail/<int:user_id>/', UserDetailView.as_view(), name='user_detail'),
    path('toggle-user-status/<int:user_id>/', ToggleUserStatusView.as_view(), name='toggle_user_status'),
    path('ban-user/', BanUserView.as_view(), name='ban_user'),
    path('user/modify-balance/', ModifyUserBalanceView.as_view(), name='admin_modify_balance'),

]
