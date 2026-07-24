"""Access control mixins for the medical_records app."""

from django.contrib.auth.mixins import LoginRequiredMixin


class ConsultationAccessMixin(LoginRequiredMixin):
    """
    Grants access to the consultation view for:
      - Admins
      - The assigned doctor of the appointment
    Anyone else is denied.

    Sets `self.appointment` before dispatch continues.
    """

    def dispatch(self, request, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404

        from appointments.models import Appointment

        # Not logged in — LoginRequiredMixin handles it in super()
        response = LoginRequiredMixin.dispatch(self, request, *args, **kwargs)
        if request.user.is_anonymous:
            return response

        appt = get_object_or_404(Appointment, pk=kwargs["appointment_pk"])
        self.appointment = appt

        user = request.user
        is_admin = user.is_admin
        is_owning_doctor = (
            user.role == "DOCTOR"
            and hasattr(user, "doctor_profile")
            and appt.doctor_id == user.doctor_profile.pk
        )
        if not (is_admin or is_owning_doctor):
            raise PermissionDenied(
                "Only the assigned doctor or an admin can access this consultation."
            )

        return response