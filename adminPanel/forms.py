import re

from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from Prediction.models import Asset
from Prediction.models import PredictionRound
from adminPanel.models import AdminUser


class AdminLoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'Admin Email', 'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}))
    # فیلد جدید برای مرحله دوم
    otp_code = forms.CharField(required=False, max_length=6,
                               widget=forms.TextInput(attrs={'placeholder': '6-digit OTP', 'class': 'form-control'}))


class AdminLockScreen(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "placeholder": "Enter your admin password",
            "class": "form-control"
        }),
        label="Password",
        max_length=128
    )


DURATION_UNITS = (
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
)


class AdminPredictionRoundForm(forms.ModelForm):
    assets = forms.ModelMultipleChoiceField(
        queryset=Asset.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        error_messages={'required': 'At least one asset must be selected.'}
    )

    # Timeframes configuration
    tf1_value = forms.IntegerField(min_value=1, required=True,
                                   widget=forms.NumberInput(attrs={'placeholder': 'Value', 'required': 'required'}))
    tf1_unit = forms.ChoiceField(choices=DURATION_UNITS, required=True)

    tf2_value = forms.IntegerField(min_value=1, required=False,
                                   widget=forms.NumberInput(attrs={'placeholder': 'Value'}))
    tf2_unit = forms.ChoiceField(choices=DURATION_UNITS, required=False)

    tf3_value = forms.IntegerField(min_value=1, required=False,
                                   widget=forms.NumberInput(attrs={'placeholder': 'Value'}))
    tf3_unit = forms.ChoiceField(choices=DURATION_UNITS, required=False)

    tf4_value = forms.IntegerField(min_value=1, required=False,
                                   widget=forms.NumberInput(attrs={'placeholder': 'Value'}))
    tf4_unit = forms.ChoiceField(choices=DURATION_UNITS, required=False)

    class Meta:
        model = PredictionRound
        fields = ["title", "min_bet_amount", "max_bet_amount", "admin_fee_percent"]
        widgets = {
            'title': forms.TextInput(attrs={'required': 'required', 'placeholder': 'Round Title'}),
            'min_bet_amount': forms.NumberInput(
                attrs={'required': 'required', 'placeholder': 'Min Limit (e.g. 10.00)'}),
            'max_bet_amount': forms.NumberInput(
                attrs={'required': 'required', 'placeholder': 'Max Limit (e.g. 100.00)'}),
            'admin_fee_percent': forms.NumberInput(attrs={'required': 'required', 'step': '0.01'}),
        }

    def clean(self):
        cleaned = super().clean()
        assets = cleaned.get("assets")
        min_limit = cleaned.get("min_bet_amount")
        max_limit = cleaned.get("max_bet_amount")

        if not assets:
            self.add_error('assets', "Select at least one asset.")

        if min_limit and max_limit and min_limit > max_limit:
            self.add_error('min_bet_amount', "Min limit cannot be greater than Max limit.")

        # Logic for timeframe seconds conversion...
        for i in range(1, 5):
            val = cleaned.get(f"tf{i}_value")
            unit = cleaned.get(f"tf{i}_unit")
            if val and unit:
                cleaned[f"tf{i}_seconds"] = val * (60 if unit == "minutes" else 3600)
            else:
                cleaned[f"tf{i}_seconds"] = 0
        return cleaned


class AdminRegistrationForm(forms.Form):
    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        help_text="Username may only contain letters, numbers, and underscores."
    )

    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'})
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        min_length=8,
        label="Password"
    )

    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        label="Confirm Password"
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not re.match(r'^[\w]+$', username):
            raise ValidationError("Username must contain only letters, numbers, and underscores.")

        # بررسی تکراری نبودن نام کاربری
        if AdminUser.objects.filter(username=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get('password')

        # ولیدیشن‌های اختصاصی و دستی (بدون وابستگی به تنظیمات پروژه)
        if not any(char.isdigit() for char in password):
            raise ValidationError('Password must contain at least one digit.')

        if not any(char.isupper() for char in password):
            raise ValidationError('Password must contain at least one uppercase letter.')

        if not any(char in "!@#$%^&*()_+-=" for char in password):
            raise ValidationError('Password must contain at least one special character.')

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        # چک کردن مطابقت دو رمز عبور
        if password and password_confirm and password != password_confirm:
            # انتساب خطا به فیلد تایید رمز برای نمایش بهتر در UI
            self.add_error('password_confirm', "Passwords do not match.")

        return cleaned_data


class AdminPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-control pe-5',
                'placeholder': field.label
            })


class BanUserForm(forms.Form):
    ban_reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}), required=False)
    ban_end = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
                                  required=False, label="Unban Time (optional)")
    is_banned = forms.BooleanField(required=False, label="Ban this user")
