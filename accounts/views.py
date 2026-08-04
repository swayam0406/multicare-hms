"""Views for the accounts app."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView

from .forms import AdminUserCreateForm, LoginForm
from .mixins import AdminRequiredMixin

UserModel = get_user_model()


# ---------- Auth ----------


class CustomLoginView(LoginView):
    """Bootstrap-styled login page."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class ProfileView(LoginRequiredMixin, TemplateView):
    """User's own profile summary."""

    template_name = "accounts/profile.html"


# ---------- Sprint 8 T-8.6: Admin user creation + list ----------


class UserListView(AdminRequiredMixin, ListView):
    """Admin-only list of all users with search + role filter."""

    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 30

    def get_queryset(self):
        qs = UserModel.objects.all().order_by("-date_joined")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = (
                qs.filter(
                    username__icontains=q,
                )
                | UserModel.objects.filter(
                    email__icontains=q,
                )
                | UserModel.objects.filter(
                    first_name__icontains=q,
                )
                | UserModel.objects.filter(
                    last_name__icontains=q,
                )
            )
            qs = qs.distinct().order_by("-date_joined")

        role = self.request.GET.get("role", "").strip()
        if role:
            qs = qs.filter(role=role)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search"] = self.request.GET.get("q", "").strip()
        ctx["role_filter"] = self.request.GET.get("role", "").strip()
        ctx["role_choices"] = UserModel.Role.choices
        return ctx


class AdminUserCreateView(AdminRequiredMixin, CreateView):
    """Admin-only form to provision a new staff user."""

    form_class = AdminUserCreateForm
    template_name = "accounts/user_create.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        response = super().form_valid(form)

        user = self.object
        messages.success(
            self.request,
            f"User '{user.username}' ({user.get_role_display()}) created.",
        )

        # Optional welcome email (best-effort)
        try:
            send_mail(
                subject="Your Multicare HMS account",
                message=(
                    f"Hello {user.get_full_name() or user.username},\n\n"
                    f"An account has been created for you at Multicare HMS.\n\n"
                    f"Username: {user.username}\n"
                    f"Role: {user.get_role_display()}\n\n"
                    "Please sign in and change your password on first login.\n\n"
                    "-- Multicare HMS"
                ),
                from_email=None,
                recipient_list=[user.email] if user.email else [],
                fail_silently=True,
            )
        except Exception:
            pass

        return response
