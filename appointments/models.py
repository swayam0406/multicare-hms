"""Models for the appointments app."""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from doctors.models import Doctor, DoctorAvailability
from patients.models import Patient


class AppointmentManager(models.Manager):
    """Custom manager with common appointment queries."""

    ACTIVE_STATUSES = ("SCHEDULED", "CONFIRMED", "IN_PROGRESS")

    def active(self):
        """Appointments in non-terminal states (not cancelled/no-show/completed)."""
        return self.filter(status__in=self.ACTIVE_STATUSES)

    def upcoming(self):
        return self.active().filter(scheduled_start__gte=timezone.now())

    def today_for_doctor(self, doctor):
        today = timezone.localdate()
        start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        end = start + timedelta(days=1)
        return (
            self.filter(
                doctor=doctor,
                scheduled_start__gte=start,
                scheduled_start__lt=end,
            )
            .select_related("patient", "doctor__user")
            .order_by("scheduled_start")
        )

    def for_patient(self, patient):
        return (
            self.filter(patient=patient)
            .select_related("doctor__user", "doctor__department")
            .order_by("-scheduled_start")
        )


class Appointment(models.Model):
    """A patient's scheduled visit with a doctor."""

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No-show"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    scheduled_start = models.DateTimeField(
        help_text="When the appointment is scheduled to begin.",
    )
    scheduled_end = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Auto-computed from doctor's slot duration on save.",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    reason = models.CharField(
        max_length=200,
        help_text="Chief complaint or reason for visit.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Free-form notes updated during and after the visit.",
    )
    cancelled_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reason if the appointment was cancelled.",
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booked_appointments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AppointmentManager()

    class Meta:
        db_table = "appointments_appointment"
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["-scheduled_start"]
        indexes = [
            models.Index(fields=["scheduled_start"]),
            models.Index(fields=["doctor", "scheduled_start"]),
            models.Index(fields=["patient", "scheduled_start"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            f"{self.patient.full_name} with {self.doctor.display_name} "
            f"on {self.scheduled_start:%Y-%m-%d %H:%M}"
        )

    # ---------- Behavior ----------

    def save(self, *args, **kwargs):
        # Always recompute scheduled_end from doctor's slot duration
        if self.scheduled_start and self.doctor_id:
            duration = self.doctor.consultation_duration_minutes
            self.scheduled_end = self.scheduled_start + timedelta(minutes=duration)
        super().save(*args, **kwargs)

    def clean(self):
        """
        Validate at the model layer — enforced from admin, forms, and shell.
        - No scheduling in the past.
        - No overlap with the same doctor's other active appointments.
        - Must fall within the doctor's weekly availability windows.
        """
        errors = {}

        if not self.scheduled_start:
            return

        if not self.doctor_id:
            return

        # Recompute the end (save() also does this, but clean() runs first)
        duration = self.doctor.consultation_duration_minutes
        scheduled_end = self.scheduled_start + timedelta(minutes=duration)

        # 1. Not in the past
        if self.scheduled_start < timezone.now():
            errors["scheduled_start"] = "Cannot schedule an appointment in the past."

        # 2. Doctor's availability (weekday + time window)
        weekday = self.scheduled_start.weekday()
        local_start = timezone.localtime(self.scheduled_start).time()
        local_end = timezone.localtime(scheduled_end).time()

        fits_a_window = DoctorAvailability.objects.filter(
            doctor=self.doctor,
            weekday=weekday,
            start_time__lte=local_start,
            end_time__gte=local_end,
        ).exists()
        if not fits_a_window:
            errors["scheduled_start"] = (
                "This time falls outside the doctor's available hours for "
                f"{self.scheduled_start.strftime('%A')}."
            )

        # 3. Overlap with any active appointment for this doctor
        overlap_qs = Appointment.objects.filter(
            doctor=self.doctor,
            status__in=AppointmentManager.ACTIVE_STATUSES,
            scheduled_start__lt=scheduled_end,
            scheduled_end__gt=self.scheduled_start,
        )
        if self.pk:
            overlap_qs = overlap_qs.exclude(pk=self.pk)
        if overlap_qs.exists():
            errors["scheduled_start"] = (
                "This time conflicts with another appointment for the same doctor."
            )

        if errors:
            raise ValidationError(errors)

    # ---------- Convenience ----------

    @property
    def is_active(self) -> bool:
        return self.status in AppointmentManager.ACTIVE_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            self.Status.COMPLETED,
            self.Status.CANCELLED,
            self.Status.NO_SHOW,
        )

    # ---------- State-machine transitions ----------

    ALLOWED_TRANSITIONS = {
        "SCHEDULED": {"CONFIRMED", "CANCELLED", "NO_SHOW"},
        "CONFIRMED": {"IN_PROGRESS", "CANCELLED", "NO_SHOW"},
        "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
        "NO_SHOW": set(),
    }

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def available_transitions(self) -> list[str]:
        return sorted(self.ALLOWED_TRANSITIONS.get(self.status, set()))
