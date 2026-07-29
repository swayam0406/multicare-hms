"""Signals for the billing app."""

from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from appointments.models import Appointment


@receiver(post_save, sender=Appointment)
def create_bill_when_completed(sender, instance, created, **kwargs):
    """
    When an appointment transitions to COMPLETED, create a DRAFT bill
    pre-populated with the doctor's consultation fee.

    Skip if:
      - Appointment was just created (not a status transition)
      - Not moving to COMPLETED
      - Bill already exists (idempotent)
    """
    if created:
        return
    if instance.status != "COMPLETED":
        return

    # Idempotent — don't recreate
    if hasattr(instance, "bill"):
        return

    # Late imports to avoid app-loading race conditions
    from billing.models import Bill, BillItem, ServiceCatalog

    bill = Bill.objects.create(
        appointment=instance,
        patient=instance.patient,
        created_by=instance.booked_by,
    )

    # Try to attach a "consultation" line item.
    # First look for a matching service in the catalog; fall back to raw fee.
    consultation_service = (
        ServiceCatalog.objects.filter(
            category=ServiceCatalog.Category.CONSULTATION,
            is_active=True,
        )
        .order_by("code")
        .first()
    )

    if consultation_service and instance.doctor.consultation_fee > Decimal("0.00"):
        BillItem.objects.create(
            bill=bill,
            service=consultation_service,
            description=f"Consultation with {instance.doctor.display_name}",
            unit_price=instance.doctor.consultation_fee,
            quantity=1,
        )
    # No else: if no catalog service or zero fee, bill stays empty
    # and the receptionist adds items manually.
