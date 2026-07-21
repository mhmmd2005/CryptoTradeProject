from django.urls import path

from .views import WalletWithdrawView, CreateDepositView, NowPaymentsCallbackView, LatestTransaction, \
    DepositTransactionList, WithdrawTransactionList, GetPaymentStatusView, UserWalletStatsAPI, RecentActivityView, \
    UserWalletCashFlowAPI

urlpatterns = [
    path('my-wallet/', WalletWithdrawView.as_view(), name='buy-and-sell'),
    path("transactions/latest/", LatestTransaction.as_view(), name="latest_transactions"),
    path('activity/recent/', RecentActivityView.as_view(), name='recent-activity'),
    path("wallet/deposit/", CreateDepositView.as_view(), name="create-deposit"),
    path("wallet/get-status/", GetPaymentStatusView.as_view(), name="get-payment-status"),

    path("wallet/nowpayments/callback/", NowPaymentsCallbackView.as_view(), name="now-payments-callback"),
    path('transactions/deposit/', DepositTransactionList.as_view(), name='deposit-transaction-list'),
    path('transactions/withdraw/', WithdrawTransactionList.as_view(), name='withdraw-transaction-list'),
    path('api/wallet-stats/', UserWalletStatsAPI.as_view(), name='wallet_stats_api'),
    path('api/wallet-cashflow/', UserWalletCashFlowAPI.as_view(), name='wallet_cashflow_api'),

]
