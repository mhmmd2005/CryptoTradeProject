import json
import time
import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model, authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.generic import FormView, View

# Optimized Imports
from accounts.forms import (
    RegisterForm, LoginForm, TwoStepLoginForm,
    ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm, LockScreenForm
)
from .tasks import send_activation_email, send_reset_email

User = get_user_model()


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data["email"].lower()
        password = form.cleaned_data["password1"]

        token = str(uuid.uuid4())
        # Store registration data in cache for 2 minutes
        cache.set(f"register:{token}", {"email": email, "password": password}, timeout=120)

        activation_link = self.request.build_absolute_uri(
            reverse("activate_temp", kwargs={"token": token})
        )

        send_activation_email.delay(email, activation_link)

        messages.success(
            self.request,
            "Registration successful! Please check your email to activate your account within 2 minutes."
        )
        return self.render_to_response(self.get_context_data(form=form))


class ActivateTempUserView(View):
    def get(self, request, token, *args, **kwargs):
        data = cache.get(f"register:{token}")
        if not data:
            messages.error(request, "Activation link is invalid or expired.")
            return redirect("register")

        # Create user instance after verification
        user = User.objects.create_user(
            username=data["email"],
            email=data["email"],
            password=data["password"],
            is_active=True
        )
        cache.delete(f"register:{token}")
        messages.success(request, "Your account has been activated! You can now log in.")
        return redirect("login")


class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("dashboard:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['next_url'] = self.request.GET.get("next") or self.request.POST.get("next", "")
        return context

    def form_valid(self, form):
        email = form.cleaned_data["email"].lower()
        password = form.cleaned_data["password"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(self.request, "This email is not registered.")
            return self.form_invalid(form)

        if not user.is_active:
            messages.error(self.request, "Your account is not activated yet.")
            return self.form_invalid(form)

        # Authentication (email as username)
        user_auth = authenticate(self.request, username=email, password=password)

        if user_auth:
            login(self.request, user_auth)
            messages.success(self.request, "Login successful.", extra_tags="dashboard_only")

            # Handling Two-Factor Logic
            two_factor = getattr(user_auth, 'two_factor', None)
            if two_factor and two_factor.is_enabled and not two_factor.is_verified:
                return redirect("two-step-verification")

            return redirect(self.get_success_url())
        else:
            messages.error(self.request, "Incorrect password.")
            return self.form_invalid(form)

    def get_success_url(self):
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if next_url and next_url.startswith("/"):
            return next_url
        return str(self.success_url)


class TwoStepVerificationView(LoginRequiredMixin, View):
    template_name = "accounts/two-step-verification.html"

    def get(self, request):
        two_factor = getattr(request.user, 'two_factor', None)
        if not two_factor or not two_factor.is_enabled:
            return redirect("dashboard:dashboard")

        form = TwoStepLoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = TwoStepLoginForm(request.POST)
        two_factor = getattr(request.user, 'two_factor', None)

        if not two_factor or not two_factor.is_enabled:
            return redirect("dashboard:dashboard")

        if form.is_valid():
            code = form.cleaned_data['code']
            if two_factor.verify_token(code):
                two_factor.is_verified = True
                two_factor.save()
                request.session['two_step_verified'] = True
                messages.success(request, "Two-Step Verification successful!")
                return redirect("dashboard:dashboard")
            else:
                messages.error(request, "Invalid code. Please try again.")
        return render(request, self.template_name, {'form': form})


class ChangePasswordView(LoginRequiredMixin, FormView):
    template_name = "accounts/change_password.html"
    form_class = ChangePasswordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.request.user.set_password(form.cleaned_data["new_password"])
        self.request.user.save()
        update_session_auth_hash(self.request, self.request.user)
        return JsonResponse({
            'success': True,
            'redirect_url': reverse("dashboard:dashboard")
        })

    def form_invalid(self, form):
        return JsonResponse({
            'success': False,
            'errors': form.errors
        })


class ForgotPasswordView(FormView):
    template_name = "accounts/forgot_password.html"
    form_class = ForgotPasswordForm
    success_url = reverse_lazy("forgot_password")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        users = User.objects.filter(email=email)

        if users.exists():
            for user in users:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                timestamp = int(time.time())

                reset_link = self.request.build_absolute_uri(
                    reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token}) + f"?ts={timestamp}"
                )
                send_reset_email.delay(email, user.username, reset_link)

        messages.success(self.request, "Done. Please check your email.", extra_tags="forgot-password-msg")
        return super().form_valid(form)


class ResetPasswordView(FormView):
    template_name = "accounts/reset_password.html"
    form_class = ResetPasswordForm
    success_url = reverse_lazy("login")

    def dispatch(self, request, *args, **kwargs):
        self.uidb64 = kwargs.get("uidb64")
        self.token = kwargs.get("token")

        try:
            uid = urlsafe_base64_decode(self.uidb64).decode()
            self.user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            self.user = None

        ts = int(request.GET.get("ts", 0))
        if ts == 0 or time.time() - ts > 120:
            messages.error(request, "This link has expired.")
            return redirect("forgot_password")

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if self.user is not None and default_token_generator.check_token(self.user, self.token):
            new_password = form.cleaned_data["new_password"]
            self.user.set_password(new_password)
            self.user.save()
            messages.success(
                self.request,
                "Your password has been successfully changed. You can now log in.",
                extra_tags="reset-password-msg"
            )
            return super().form_valid(form)
        else:
            messages.error(self.request, "This link is invalid.")
            return redirect("forgot_password")


class LogoutView(View):
    def get(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, "You have successfully logged out.")
        return redirect("login")


class LockScreenView(LoginRequiredMixin, View):
    template_name = 'Lock_screen/Lock-screen.html'

    def get(self, request):
        request.session['locked'] = True
        form = LockScreenForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        try:
            data = json.loads(request.body)
            password = data.get('password', '').strip()

            if request.user.check_password(password):
                request.session['locked'] = False
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
