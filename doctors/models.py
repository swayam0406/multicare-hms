"""Models for the doctors app."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Department(models.Model):
    """A hospital department (e.g., Cardiology, Radiology, Emergency)."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctors_department"
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().strip()
        super().save(*args, **kwargs)


class DoctorManager(models.Manager):
    """Custom manager with active-doctor helpers."""

    def available(self):
        return self.filter(is_available_for_booking=True, user__is_active=True)


class Doctor(models.Model):
    """
    A doctor's professional profile.
    OneToOne with a User account (role=DOCTOR).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
        limit_choices_to={"role": "DOCTOR"},
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="doctors",
    )
    license_number = models.CharField(max_length=50, unique=True)
    specialty = models.CharField(
        max_length=100,
        help_text="Sub-specialty within the department (e.g., 'Interventional Cardiology').",
    )
    qualifications = models.CharField(
        max_length=200,
        help_text="Degrees, e.g., 'MBBS, MD (Cardiology)'.",
    )
    years_of_experience = models.PositiveIntegerField(default=0)
    consultation_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Fee per consultation in ₹.",
    )
    consultation_duration_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(5)],
        help_text="Length of one appointment slot, in minutes.",
    )
    bio = models.TextField(blank=True)
    is_available_for_booking = models.BooleanField(
        default=True,
        help_text="Uncheck to temporarily stop new appointments.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DoctorManager()

    class Meta:
        db_table = "doctors_doctor"
        verbose_name = "Doctor"
        verbose_name_plural = "Doctors"
        ordering = ["user__first_name", "user__last_name"]
        indexes = [
            models.Index(fields=["department"]),
            models.Index(fields=["is_available_for_booking"]),
        ]

    def __str__(self):
        return f"Dr. {self.full_name} ({self.department.code})"

    @property
    def full_name(self) -> str:
        return self.user.get_full_name() or self.user.username

    @property
    def display_name(self) -> str:
        """Doctor's name with 'Dr.' prefix."""
        return f"Dr. {self.full_name}"


class DoctorAvailability(models.Model):
    """
    A doctor's recurring weekly availability window.
    A doctor can have multiple windows per day (e.g., 9-12 morning + 5-7 evening).
    """

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="availabilities",
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        db_table = "doctors_availability"
        verbose_name = "Availability slot"
        verbose_name_plural = "Availability slots"
        ordering = ["doctor", "weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "weekday", "start_time"],
                name="unique_doctor_weekday_start",
            ),
            models.CheckConstraint(
                condition=models.Q(start_time__lt=models.F("end_time")),
                name="availability_start_before_end",
            ),
        ]

    def __str__(self):
        return (
            f"{self.doctor.display_name} — {self.get_weekday_display()} "
            f"{self.start_time.strftime('%H:%M')}–{self.end_time.strftime('%H:%M')}"
        )
