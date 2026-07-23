"""
Role-based access control (RBAC) mixins for class-based views.

Usage:
    class DoctorDashboardView(DoctorRequiredMixin, TemplateView):
        template_name = 'doctors/dashboard.html'

All mixins:
    - Redirect anonymous users to LOGIN_URL (via LoginRequiredMixin).
    - Deny authenticated users lacking the required role with HTTP 403.
    - Show a Django messages framework alert on denial.
"""

from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    UserPassesTestMixin,
)


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Generic base — require a user to hold one of `allowed_roles`.

    Subclass and set `allowed_roles` as a list of Role values,
    or override `test_func()` for custom logic.
    """

    allowed_roles: list[str] = []
    permission_denied_message = "You do not have permission to access this page."
    raise_exception = False  # Redirect on failure; set True to force 403

    def test_func(self) -> bool:
        user = self.request.user
        return user.is_authenticated and user.role in self.allowed_roles

    def handle_no_permission(self):
        """Flash a message before Django's default redirect / 403 behavior."""
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
        return super().handle_no_permission()


# ---------- Role-specific convenience mixins ----------

class AdminRequiredMixin(RoleRequiredMixin):
    """Only users with role=ADMIN may access."""
    allowed_roles = ['ADMIN']
    permission_denied_message = "Admins only. You do not have permission."


class DoctorRequiredMixin(RoleRequiredMixin):
    """Only users with role=DOCTOR may access."""
    allowed_roles = ['DOCTOR']
    permission_denied_message = "This area is restricted to doctors."


class NurseRequiredMixin(RoleRequiredMixin):
    """Only users with role=NURSE may access."""
    allowed_roles = ['NURSE']
    permission_denied_message = "This area is restricted to nurses."


class ReceptionistRequiredMixin(RoleRequiredMixin):
    """Only users with role=RECEPTIONIST may access."""
    allowed_roles = ['RECEPTIONIST']
    permission_denied_message = "This area is restricted to receptionists."


class PatientRequiredMixin(RoleRequiredMixin):
    """Only users with role=PATIENT may access."""
    allowed_roles = ['PATIENT']
    permission_denied_message = "This area is restricted to patients."


# ---------- Common combined mixins ----------

class StaffRequiredMixin(RoleRequiredMixin):
    """Any clinical or administrative staff (excludes patients)."""
    allowed_roles = ['ADMIN', 'DOCTOR', 'NURSE', 'RECEPTIONIST']
    permission_denied_message = "Staff access only."


class ClinicalRequiredMixin(RoleRequiredMixin):
    """Clinical roles only — doctors and nurses."""
    allowed_roles = ['DOCTOR', 'NURSE']
    permission_denied_message = "Clinical staff access only."