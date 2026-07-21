# from Notification.models import Notification
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django.views.generic import TemplateView

from UserPanel.forms import TicketForm
from UserPanel.models import UserTicket, FAQCategory
from dashboard.models import Notification


# Create your views here.

class UserAddTicketView(LoginRequiredMixin, View):
    template_name = 'userpanel/ticket/add-ticket.html'

    def get(self, request):
        form = TicketForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = TicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            if not ticket.start_date:
                ticket.start_date = timezone.localdate()

            ticket.save()

            messages.success(request, "Your ticket has been successfully submitted.", extra_tags='success-ticket')
            return redirect('add-ticket')

        return render(request, self.template_name, {'form': form})


class MyTicketView(LoginRequiredMixin, View):
    template_name = 'userpanel/ticket/my-ticket.html'

    def get(self, request):
        search_query = request.GET.get('search', '')
        status_filter = request.GET.get('status', 'all')
        # منطق دقیقاً مشابه کد ادمین: دریافت تمام تیکت‌های کاربر
        tickets = UserTicket.objects.filter(user=request.user).order_by('-created_at')

        if status_filter == 'open':
            tickets = tickets.exclude(status='answered')
        elif status_filter == 'answered':
            tickets = tickets.filter(status='answered')

        # اعمال فیلتر جستجو (بدون تغییر در منطق شما)
        if search_query:
            tickets = tickets.filter(
                Q(title__icontains=search_query) |
                Q(ticket_id__icontains=search_query)
            )

        # پیجینیشن کاملاً مطابق با منطق کد ادمینی که فرستادید
        paginator = Paginator(tickets, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        current_page = page_obj.number
        total_pages = paginator.num_pages
        # محدوده صفحات (صفحه قبل، فعلی، صفحه بعد)
        start_page = max(current_page - 1, 1)
        end_page = min(current_page + 1, total_pages)
        page_range = range(start_page, end_page + 1)

        context = {
            'page_obj': page_obj,
            'page_range': page_range,
            'search_query': search_query,
            'status_filter': status_filter,  #
            'tickets': page_obj,
        }

        # بررسی درخواست HTMX (دقیقاً مشابه منطق ادمین برای پایداری سرچ)
        if request.headers.get('HX-Request'):
            return render(request, self.template_name, context)

        return render(request, self.template_name, context)


@method_decorator(require_POST, name='dispatch')
class CreateSupportTicketView(LoginRequiredMixin, View):
    """
    ویو برای ایجاد تیکت پشتیبانی توسط کاربر (حتی در حالت بن)
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON data.'}, status=400)

        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()

        if not subject or not message:
            return JsonResponse({'success': False, 'message': 'Subject and message are required.'}, status=400)

        # ایجاد تیکت جدید
        ticket = UserTicket.objects.create(
            user=request.user,
            title=subject,
            message=message,
            department='General',  # می‌توانید از داده‌های ارسالی هم بگیرید
            priority='medium',  # پیش‌فرض
            status='open'
        )

        return JsonResponse({'success': True, 'message': 'Ticket submitted successfully.'})


@login_required
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(UserTicket, id=ticket_id, user=request.user)
    last_reply = ticket.replies.order_by('-created_at').first()
    Notification.objects.filter(
        user=request.user,
        link__icontains=str(ticket_id),
        is_read=False
    ).update(is_read=True)

    if request.method == 'POST':
        if ticket.replies.exists():
            messages.error(request, 'This ticket has been replied to and is now locked for editing.')
            return redirect('ticket_detail', ticket_id=ticket.id)

        ticket.title = request.POST.get('title')
        ticket.priority = request.POST.get('priority')
        ticket.department = request.POST.get('department')

        new_date = request.POST.get('start_date')
        if new_date:
            ticket.start_date = new_date

        ticket.message = request.POST.get('message')
        ticket.save()

        messages.success(request, 'Ticket updated successfully.', extra_tags='success-ticket')
        return redirect('my-ticket')

    return render(request, 'userpanel/ticket/ticketDetail.html', {
        'ticket': ticket,
        'last_reply': last_reply
    })


@login_required
@require_POST  # فقط اجازه متد POST را می‌دهد، در غیر این صورت 405 می‌دهد
def delete_ticket(request, pk):
    try:
        # لایه امنیتی: فقط تیکتِ خودِ کاربر
        ticket = get_object_or_404(UserTicket, pk=pk, user=request.user)
        ticket.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        # در صورت بروز خطای غیرمنتظره، سیستم کرش نمی‌کند
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


class AllNotifications(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'userpanel/notifications/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 10

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user, is_hidden=False)
        query = self.request.GET.get('search')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(message__icontains=query) | Q(category__icontains=query))
        return queryset.order_by('-created_at')

    def get(self, request, *args, **kwargs):
        # این شرط باعث می‌شود فقط در لودِ اولیه، وضعیتِ 'خوانده شده' آپدیت شود
        if not request.GET.get('search'):
            Notification.objects.filter(user=self.request.user, is_read=False).update(is_read=True)
        return super().get(request, *args, **kwargs)


class ArchiveNotificationsView(LoginRequiredMixin, View):
    def post(self, request):
        notification_ids = request.POST.getlist('ids[]')
        # مخفی کردن اعلان‌های انتخاب شده
        Notification.objects.filter(id__in=notification_ids, user=request.user).update(is_hidden=True)
        return JsonResponse({'status': 'success'})


class FAQView(LoginRequiredMixin, TemplateView):
    template_name = 'userpanel/FAQ/faq.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # دریافت تمام دسته‌ها به همراه سوالاتشان
        context['categories'] = FAQCategory.objects.prefetch_related('faqs').all()
        return context


@login_required
def update_email_settings(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            is_enabled = data.get('email_enabled')

            profile = request.user.profile
            profile.email_notifications_enabled = bool(is_enabled)
            profile.save()
            return JsonResponse({'status': 'success'})
        except Exception:
            return JsonResponse({'status': 'error'}, status=400)
    return JsonResponse({'status': 'error'}, status=405)  # Method Not Allowed


class BannedPageView(LoginRequiredMixin, TemplateView):
    template_name = 'userpanel/banned/banned_page.html'

    def dispatch(self, request, *args, **kwargs):
        profile = request.user.profile
        if profile and profile.is_banned:
            self.show_error = False
        else:
            if not request.session.get('was_banned', False):
                self.show_error = True
            else:
                self.show_error = False
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        profile = user.profile

        if self.show_error:
            context['error_message'] = 'You are not allowed to access this page.'
            return context

        is_banned = profile.is_banned
        if not is_banned and self.request.session.pop('was_banned', False):
            context['just_unbanned'] = True
        else:
            context['just_unbanned'] = False

        if is_banned:
            self.request.session['was_banned'] = True

        context['ban_reason'] = profile.ban_reason
        context['ban_start'] = profile.ban_start
        context['ban_end'] = profile.ban_end
        context['is_permanent'] = profile.ban_end is None
        return context
