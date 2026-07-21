# context_processors.py
from Prediction.models import Prediction
from UserPanel.models import UserTicket
from adminPanel.models import PlatformRevenue
from dashboard.models import ProfileApprovalStatus, UserProfile
from wallet.models import WithdrawRequest, WalletTransaction


def admin_counters(request):
    if hasattr(request, 'admin_user') or (request.user.is_authenticated and request.user.is_staff):

        revenue_account = PlatformRevenue.get_revenue_account(currency_code='usdttrc20')
        total_fees = revenue_account.balance

        return {

            'open_tickets_count': UserTicket.objects.filter(status='open').count(),
            'pending_kyc_count': ProfileApprovalStatus.objects.filter(status='pending').count(),
            'pending_withdraws_count': WithdrawRequest.objects.filter(status='pending').count(),
            'total_users_count': UserProfile.objects.count(),
            'total_deposits_count': WalletTransaction.objects.filter(type='deposit',  status__in=['success', 'pending']).count(),
            'total_withdraws_count': WithdrawRequest.objects.filter(status='done').count(),
            'total_predictions_count': Prediction.objects.count(),
            'total_fees_earned': total_fees,
        }
    return {}
