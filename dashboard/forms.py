# from flatpickr.widgets import DatePickerInput

from django import forms

from .models import UserProfile


# from flatpickr.widgets import DatePickerInput  # اگر از flatpickr استفاده می‌کنید


class UserProfileForm(forms.ModelForm):
    profile_image = forms.ImageField(required=False, label="Profile Image")

    class Meta:
        model = UserProfile
        fields = [
            "first_name",
            "last_name",
            "phone_number",
            "city",
            "country",
            "zipcode",
            "description",
            "profile_image"
        ]
        widgets = {
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Briefly describe yourself...",
                "rows": 4
            }),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter first name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter last name"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter phone number"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "country": forms.TextInput(attrs={"class": "form-control", "placeholder": "Country"}),
            "zipcode": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Zip", "minlength": 5, "maxlength": 6}),
        }

    def clean(self):
        cleaned_data = super().clean()
        required_fields = ["first_name", "last_name", "phone_number", "city", "country", "zipcode"]

        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, "This field is required.")
        return cleaned_data


class CustomUsernameForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['custom_username', 'avatar']
        widgets = {
            'custom_username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a unique username'
            })
        }
        labels = {
            'custom_username': 'Choose a username'
        }

    def clean_custom_username(self):
        username = self.cleaned_data.get('custom_username')
        if username:
            # حذف فاصله‌ها و تبدیل به حروف کوچک (اختیاری)
            username = username.strip().lower()
            # بررسی یکتایی (به غیر از خود کاربر)
            qs = UserProfile.objects.exclude(pk=self.instance.pk).filter(custom_username=username)
            if qs.exists():
                raise forms.ValidationError('This username is already taken. Please choose another.')
        return username


class DisableTwoStepForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control text-center', 'placeholder': 'Account password'}),
        max_length=128,
        required=True,
        label="Account Password"
    )
    code = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control text-center', 'maxlength': '6', 'placeholder': '6-digit code'}),
        max_length=6,
        min_length=6,
        required=True,
        label="6-Digit Code"
    )
