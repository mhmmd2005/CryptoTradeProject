from django.urls import path

from Prediction.views import PredictionView, ActiveRoundAPI, PlaceOrderAPI, \
    next_tf, get_wallet_balance, api_get_active_locks, UserDashboardStatsAPI,PredictionHistoryView

urlpatterns = [

    # تغییر نام در URLها برای کلاس بالاتر
    path("trading/<str:symbol>/", PredictionView.as_view(), name="prediction"),
    path("Trading/", PredictionView.as_view(), name="prediction-default"),

    path('api/user-stats/', UserDashboardStatsAPI.as_view(), name='user_stats_api'),
    # path('round/<int:round_id>/settle/', SettleRoundView.as_view(), name='settle-round'),
    # گرفتن راند فعال برای یک دارایی و تایم‌فریم مشخص
    path('api/active-round/<int:asset_id>/<str:timeframe>/', ActiveRoundAPI.as_view(), name='active_round_api'),

    # ثبت پیش‌بینی (POST با body JSON)
    path('api/place-order/', PlaceOrderAPI.as_view(), name='place_order_api'),
    path('api/wallet-balance/', get_wallet_balance, name='get_wallet_balance'),
    path('api/get-active-locks/', api_get_active_locks, name='api_get_active_locks'),
    path('api/next_tf/', next_tf, name='next_tf'),
    path('predictions/history/', PredictionHistoryView.as_view(), name='prediction-history'),
]
