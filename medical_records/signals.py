"""Signals for the medical_records app."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from appointments.models import Appointment


@receiver(post_save, sender=Appointment)
def lock_medical_record_when_completed(sender, instance, created, **kwargs):
    """
    When an appointment reaches COMPLETED, lock its medical record
    (if one exists). Locking is idempotent.
    """
    if created:
        return
    if instance.status != "COMPLETED":
        return
    mr = getattr(instance, "medical_record", None)
    if mr and not mr.is_locked:
        mr.lock()
