"""Views for the accounts app."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


class CustomLoginView(LoginView):
    """LoginView with a welcome flash message."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        name = user.get_full_name() or user.username
        messages.success(
            self.request,
            f"Welcome back, {name}! You are signed in as {user.get_role_display()}.",
        )
        return response


class CustomLogoutView(LogoutView):
    """LogoutView with a farewell flash message."""

    next_page = reverse_lazy("core:home")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.info(request, "You have been signed out. See you again soon.")
        return super().dispatch(request, *args, **kwargs)


class ProfileView(LoginRequiredMixin, TemplateView):
    """Display the logged-in user's profile information."""

    template_name = "accounts/profile.html"
