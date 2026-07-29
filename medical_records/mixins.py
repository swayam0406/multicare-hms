"""Access control mixins for the medical_records app."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404


class ConsultationAccessMixin(LoginRequiredMixin):
    """
    Grants access to the consultation view for:
      - Admins
      - The assigned doctor of the appointment
    Anyone else is denied.

    Sets `self.appointment` before the actual handler runs.
    """

    def dispatch(self, request, *args, **kwargs):
        # If not authenticated, LoginRequiredMixin's handle_no_permission redirects.
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # Look up appointment BEFORE the handler runs.
        from appointments.models import Appointment
        self.appointment = get_object_or_404(
            Appointment, pk=kwargs["appointment_pk"]
        )

        # RBAC
        user = request.user
        is_admin = user.is_admin
        is_owning_doctor = (
            user.role == "DOCTOR"
            and hasattr(user, "doctor_profile")
            and self.appointment.doctor_id == user.doctor_profile.pk
        )
        if not (is_admin or is_owning_doctor):
            raise PermissionDenied(
                "Only the assigned doctor or an admin can access this consultation."
            )

        return super().dispatch(request, *args, **kwargs)