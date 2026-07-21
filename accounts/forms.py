import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation

User = get_user_model()  # Using custom User model


class RegisterForm(forms.Form):
    email = forms.EmailField(label="Email")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError("This email has already been registered.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'\d', password):
            raise forms.ValidationError("Password must contain at least one number.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise forms.ValidationError("Password must contain at least one special character.")
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Password and its confirmation do not match.")
        return cleaned


class ChangePasswordForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        # Retrieve user from view (passed via get_form_kwargs)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get("old_password")
        if not self.user.check_password(old_password):
            raise forms.ValidationError("Current password is incorrect.")
        return old_password

    def clean(self):
        """
        Merged both validation logic blocks into a single clean method.
        In Python, you cannot have two methods with the same name;
        the second one will overwrite the first.
        This version executes ALL your original logic.
        """
        cleaned_data = super().clean()
        old_password = cleaned_data.get("old_password")
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        # Logic Block 1: Confirmation Match
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', "New password and confirmation do not match.")

        # Logic Block 2: Django built-in validation (settings.py)
        if new_password:
            try:
                password_validation.validate_password(new_password, self.user)
            except forms.ValidationError as e:
                self.add_error('new_password', e)

        # Logic Block 3: Old vs New Difference
        if old_password and new_password and old_password == new_password:
            self.add_error("new_password", "New password must be different from the old password.")

        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        max_length=300,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter Your Email'})
    )


class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control pe-5 password-input",
            "placeholder": "Enter password",
            "id": "password-input",
            "pattern": "(?=.*\\d)(?=.*[a-z])(?=.*[A-Z]).{8,}",
            "aria-describedby": "passwordInput",
            "onpaste": "return false",
            "required": True
        })
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control pe-5 password-input",
            "placeholder": "Confirm password",
            "id": "confirm-password-input",
            "pattern": "(?=.*\\d)(?=.*[a-z])(?=.*[A-Z]).{8,}",
            "onpaste": "return false",
            "required": True
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get("new_password", "").strip()
        pw2 = cleaned_data.get("confirm_password", "").strip()

        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data


class TwoStepLoginForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center bg-light border-light small-code-input',
            'placeholder': '6-digit code',
            'inputmode': 'numeric',
        })
    )

    def clean_code(self):
        code = self.cleaned_data.get('code', '')
        if not code.isdigit():
            raise forms.ValidationError("Code must be numeric.")
        if len(code) != 6:
            raise forms.ValidationError("Code must be exactly 6 digits.")
        return code


class LockScreenForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Enter Password',
                'class': 'form-control',
                'id': 'userpassword',
            }
        ),
        label='Password',
        required=True
    )


class TwoStepVerificationForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        label="Verification Code",
        widget=forms.TextInput(attrs={"placeholder": "Enter code"})
    )

    def clean_code(self):
        code = self.cleaned_data['code']
        if not code.isdigit():
            raise forms.ValidationError("Code must be numeric.")
        if len(code) != 6:
            raise forms.ValidationError("Code must be 6 digits.")
        return code
