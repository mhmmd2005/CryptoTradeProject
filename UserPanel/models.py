import random
import pyotp
import string
from django.urls import reverse
from django.db import models

from accounts.models import User


def generate_ticket_id(length=10):
    """تولید شناسه ۱۰ کاراکتری شامل حروف و حداکثر ۲ عدد بدون خط فاصله"""
    letters = string.ascii_uppercase
    digits = string.digits

    # انتخاب تعداد اعداد (۰ تا ۲ عدد)
    num_digits = random.randint(0, 2)
    num_letters = length - num_digits

    # انتخاب تصادفی از هر نوع
    chosen_letters = random.choices(letters, k=num_letters)
    chosen_digits = random.choices(digits, k=num_digits)

    # ترکیب و درهم‌ریختن ترتیب نهایی
    all_chars = chosen_letters + chosen_digits
    random.shuffle(all_chars)

    return ''.join(all_chars)


class UserTicket(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('important', 'Important'),
    ]

    DEPARTMENT_CHOICES = [
        ('General', 'General'),
        ('Security', 'Security'),
        ('Payment', 'Payment'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    ticket_id = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    title = models.CharField(max_length=200, null=True, blank=True)
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, default='low')
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES, default='General')
    start_date = models.DateField(blank=True, null=True)
    message = models.TextField()

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('answered', 'answered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    def get_absolute_url(self):
        try:
            # بر اساس path('ticket/detail/<int:ticket_id>/', ticket_detail, name='ticket_detail')
            return reverse('dashboard:ticket_detail', kwargs={'ticket_id': self.pk})
        except Exception:
            return reverse('my-ticket')


class UserTwoFactor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='two_factor')
    secret_key = models.CharField(max_length=32, blank=True, null=True)
    is_enabled = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}"

    def get_absolute_url(self):
        return reverse('profile-twostep')

    def verify_token(self, code: str) -> bool:
        """
        اعتبارسنجی کد ۶ رقمی TOTP با استفاده از secret_key
        """
        if not self.secret_key or not code:
            return False

        # تبدیل کد به رشته و حذف فاصله‌های احتمالی
        clean_code = str(code).strip()

        totp = pyotp.TOTP(self.secret_key)
        # valid_window=1 تلورانس زمانی ۳۰ ثانیه‌ای برای ناهماهنگی جزئی ساعت سرور و کاربر ایجاد می‌کند
        return totp.verify(clean_code, valid_window=1)


class FAQCategory(models.Model):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title


class FAQ(models.Model):
    category = models.ForeignKey(FAQCategory, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=255)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question

    def get_absolute_url(self):
        return reverse('faq')
