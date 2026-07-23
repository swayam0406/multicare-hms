"""Shared validators used across HMS apps."""

from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+?\d{10,15}$',
    message='Phone number must be 10 to 15 digits, optionally starting with +.',
)

pincode_validator = RegexValidator(
    regex=r'^\d{6}$',
    message='Enter a valid 6-digit Indian PIN code.',
)