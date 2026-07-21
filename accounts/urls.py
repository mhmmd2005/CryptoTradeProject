from django.urls import path

from accounts.views import RegisterView, ActivateTempUserView, LoginView, LogoutView, ChangePasswordView, \
    ForgotPasswordView, ResetPasswordView, TwoStepVerificationView, LockScreenView

from dashboard.views import LandingPageView

urlpatterns = [
    path("sign_up/", RegisterView.as_view(), name="register"),
    path("activate-temp/<str:token>/", ActivateTempUserView.as_view(), name="activate_temp"),
    path("sign_in/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/<uidb64>/<token>/", ResetPasswordView.as_view(), name="password_reset_confirm"),
    # path("resend-code/", ResendTwoFactorCodeView.as_view(), name="resend_code"),
    path("two-step-verification/", TwoStepVerificationView.as_view(), name="two-step-verification"),
    # path("show-qr/", ShowQRView.as_view(), name="show_qr"),
    path('lock/', LockScreenView.as_view(), name='lock_screen'),
    path('', LandingPageView.as_view(), name='landing-page'),
]
