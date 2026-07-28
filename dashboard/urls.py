from django.urls import path

from .views import DashboardView, ProfileSettingsView, TwoStepVerifyView, DisableTwoStepView, mark_notification_read, \
    notifications_dropdown, mark_all_notifications_read, CustomUsernameView, MarketDataView, BinanceTickerProxyView, \
    ExecuteInternalTradeView, InternalTradeHistoryView, GlobalSearchView, KeepAliveView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('profile/setting/', ProfileSettingsView.as_view(), name='profile-setting'),
    path('profile/setting/password/', ProfileSettingsView.as_view(), {'tab': 'password'}, name='profile-password'),
    path('profile/setting/two-step/', ProfileSettingsView.as_view(), {'tab': 'twostep'}, name='profile-twostep'),

    path('verify-two-step/', TwoStepVerifyView.as_view(), name='verify_two_step'),
    path('disable-two-step/', DisableTwoStepView.as_view(), name='disable_two_step'),

    path('notifications/', notifications_dropdown, name='notifications_dropdown'),
    path('notifications/mark-read/', mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', mark_all_notifications_read, name='mark-all-notifications-read'),

    path('profile/custom-username/', CustomUsernameView.as_view(), name='custom_username'),
    path('api/market-data/', MarketDataView.as_view(), name='market_data'),
    path('api/market-tickers/', BinanceTickerProxyView.as_view(), name='market_tickers'),
    path('api/execute-trade/', ExecuteInternalTradeView.as_view(), name='execute_trade'),
    path('trade-history/', InternalTradeHistoryView.as_view(), name='internal-trade-history'),
    path("global-search/", GlobalSearchView.as_view(), name="global-search"),
    path('keep-alive/', KeepAliveView.as_view(), name='keep_alive'), ]
