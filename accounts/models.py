"""
Custom User model for Multicare HMS.

Extends Django's AbstractUser to add role-based access control (RBAC)
and hospital-specific fields.
"""

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """
    Custom user with role, phone, and profile fields.

    Roles drive access control across the HMS.
    All hospital staff and patients are stored in this single table.
    """

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        DOCTOR = 'DOCTOR', 'Doctor'
        NURSE = 'NURSE', 'Nurse'
        RECEPTIONIST = 'RECEPTIONIST', 'Receptionist'
        PATIENT = 'PATIENT', 'Patient'

    # Override email to make it required and unique
    email = models.EmailField(
        unique=True,
        help_text='Required. Must be a valid, unique email address.',
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PATIENT,
        help_text='Determines the user\'s access level within the HMS.',
    )

    phone_regex = RegexValidator(
        regex=r'^\+?\d{10,15}$',
        message='Phone number must be 10 to 15 digits, optionally starting with +.',
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=15,
        blank=True,
        help_text='Optional. Format: +919812345678 or 9812345678.',
    )

    date_of_birth = models.DateField(
        blank=True,
        null=True,
    )

    address = models.TextField(
        blank=True,
    )

    profile_picture = models.ImageField(
        upload_to='profile_pictures/%Y/%m/',
        blank=True,
        null=True,
    )

    is_verified = models.BooleanField(
        default=False,
        help_text='Set to True once the user has verified email or phone.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        full_name = self.get_full_name() or self.username
        return f'{full_name} ({self.get_role_display()})'

    # ---------- Role helper properties ----------

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_doctor(self) -> bool:
        return self.role == self.Role.DOCTOR

    @property
    def is_nurse(self) -> bool:
        return self.role == self.Role.NURSE

    @property
    def is_receptionist(self) -> bool:
        return self.role == self.Role.RECEPTIONIST

    @property
    def is_patient(self) -> bool:
        return self.role == self.Role.PATIENT