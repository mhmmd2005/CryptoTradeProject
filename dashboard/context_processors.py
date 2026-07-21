from django.contrib.auth import get_user_model

from UserPanel.models import UserTwoFactor


def notification_context(request):
    context = {
        'unread_count': 0,
        'notifications_list': [],
        'unread_notifications': [],
        'user_unread_notifications_count': 0,
        'admin_ticket_unread_count': 0,
        'admin_kyc_unread_count': 0,  # مقدار پیش‌فرض
        'admin_unread_notifications': [],
    }

    try:
        # --- بخش ادمین (جایی که سایدبار ادمین دیتا می‌گیرد) ---
        if hasattr(request, 'admin_user') and request.admin_user:
            all_admin_notifs = request.admin_user.admin_notifications.all()
            unread_qs = all_admin_notifs.filter(is_read=False)

            context.update({
                'unread_count': unread_qs.count(),
                'notifications_list': all_admin_notifs[:10],
                'unread_notifications': unread_qs[:10],
                'admin_unread_notifications': unread_qs[:10],
                # کالیبراسیون صحیح دسته‌بندی‌ها برای ادمین
                'admin_ticket_unread_count': unread_qs.filter(category='ticket').count(),
                'admin_kyc_unread_count': unread_qs.filter(category='kyc').count(),  # جابه‌جا شد به اینجا
            })

        # --- بخش کاربر ---
        elif request.user.is_authenticated:
            if hasattr(request.user, 'user_notifications'):
                unread_qs = request.user.user_notifications.filter(is_read=False)

                context.update({
                    'unread_count': unread_qs.count(),
                    'notifications_list': request.user.user_notifications.all()[:10],
                    'unread_notifications': unread_qs[:10],
                    'user_notifications': request.user.user_notifications.all()[:10],
                    'user_unread_notifications_count': unread_qs.filter(category='ticket').count(),
                })
    except Exception as e:
        print(f"JARVIS DEBUG: Context Processor Error: {e}")

    return context


def twofa_status(request):
    user = request.user
    if not user.is_authenticated:
        return {'is_2fa_enabled': False}

    User = get_user_model()
    if not isinstance(user, User):
        return {'is_2fa_enabled': False}

    try:
        twofa = UserTwoFactor.objects.filter(user=user).first()
        return {
            'is_2fa_enabled': twofa.is_enabled if twofa else False
        }
    except Exception:
        return {'is_2fa_enabled': False}


def kyc_processor(request):
    """
    Optimized KYC processor: Single query logic preserved.
    """
    if request.user.is_authenticated:
        try:
            profile = getattr(request.user, 'profile', None)
            if profile:
                status_obj = getattr(profile, 'approval_status', None)
                kyc_status = status_obj.status if status_obj else profile.status
                is_verified = (kyc_status == 'approved')
            else:
                kyc_status = 'pending'
                is_verified = False
        except Exception:
            kyc_status = 'pending'
            is_verified = False

        return {
            'kyc_status': kyc_status,
            'is_verified': is_verified
        }

    return {
        'kyc_status': 'pending',
        'is_verified': False
    }
