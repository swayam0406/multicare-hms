"""
Patient model for Multicare HMS.

A Patient may or may not have an associated User account.
Walk-ins, minors, and unconscious ER admits are registered without
a login; portal-enabled patients have user set.
"""

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max

from core.validators import phone_validator, pincode_validator


class PatientManager(models.Manager):
    """Custom manager with soft-delete helpers."""

    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)


class Patient(models.Model):
    """A hospital patient record."""

    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        OTHER = 'OTHER', 'Other'

    class BloodGroup(models.TextChoices):
        A_POS = 'A+', 'A+'
        A_NEG = 'A-', 'A-'
        B_POS = 'B+', 'B+'
        B_NEG = 'B-', 'B-'
        O_POS = 'O+', 'O+'
        O_NEG = 'O-', 'O-'
        AB_POS = 'AB+', 'AB+'
        AB_NEG = 'AB-', 'AB-'
        UNKNOWN = 'UNK', 'Unknown'

    class MaritalStatus(models.TextChoices):
        SINGLE = 'SINGLE', 'Single'
        MARRIED = 'MARRIED', 'Married'
        DIVORCED = 'DIVORCED', 'Divorced'
        WIDOWED = 'WIDOWED', 'Widowed'
        OTHER = 'OTHER', 'Other'

    patient_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text='Auto-generated hospital ID (e.g. MC-2026-00001).',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patient_profile',
        help_text='Optional link to a User account for portal access.',
    )

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    blood_group = models.CharField(
        max_length=3,
        choices=BloodGroup.choices,
        default=BloodGroup.UNKNOWN,
    )
    marital_status = models.CharField(
        max_length=20,
        choices=MaritalStatus.choices,
        blank=True,
    )

    phone = models.CharField(max_length=15, validators=[phone_validator])
    email = models.EmailField(blank=True)
    address_line = models.TextField(blank=True)
    city = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    pincode = models.CharField(
        max_length=10,
        blank=True,
        validators=[pincode_validator],
    )

    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=15,
        blank=True,
        validators=[phone_validator],
    )
    emergency_contact_relation = models.CharField(max_length=30, blank=True)

    allergies = models.TextField(
        blank=True,
        help_text='Comma-separated list of known allergies.',
    )
    chronic_conditions = models.TextField(
        blank=True,
        help_text='e.g. diabetes, hypertension.',
    )
    current_medications = models.TextField(
        blank=True,
        help_text='Currently prescribed medications.',
    )

    is_active = models.BooleanField(
        default=True,
        help_text='Soft-delete flag. Deactivated patients are hidden from staff views.',
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registered_patients',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PatientManager()

    class Meta:
        db_table = 'patients_patient'
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient_id']),
            models.Index(fields=['phone']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f'{self.patient_id} - {self.full_name}'

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = self._generate_patient_id()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_patient_id() -> str:
        """Generate a hospital-style patient ID: MC-YYYY-00001."""
        year = date.today().year
        prefix = f'MC-{year}-'

        last = (
            Patient.objects
            .filter(patient_id__startswith=prefix)
            .aggregate(Max('patient_id'))
        )
        last_id = last['patient_id__max']

        if last_id:
            last_seq = int(last_id.split('-')[-1])
            new_seq = last_seq + 1
        else:
            new_seq = 1

        return f'{prefix}{new_seq:05d}'

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def age(self) -> int:
        """Age in whole years, computed from date_of_birth."""
        today = date.today()
        dob = self.date_of_birth
        years = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            years -= 1
        return years