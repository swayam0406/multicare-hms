"""Signals for the laboratory app."""

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender="laboratory.LabOrder")
def bill_lab_order_on_completion(sender, instance, created, **kwargs):
    """
    When a LabOrder moves to COMPLETED, append each unbilled item to the
    visit's bill (bypasses draft-only rule via Bill.system_add_item).
    Idempotent — items with is_billed=True are skipped.
    """
    if created:
        return
    if instance.status != "COMPLETED":
        return

    # Late imports to avoid app-loading order issues
    from billing.models import Bill

    # Find the visit's bill (if any)
    appointment = instance.medical_record.appointment
    bill = Bill.objects.filter(appointment=appointment).first()
    if bill is None:
        # No bill exists yet — nothing to append to.
        # The appointment hasn't been completed, so no autobill signal has fired.
        # We could create one, but that complicates ownership of who created it.
        # Simpler: skip. When the appointment completes, the bill signal will fire
        # separately. If lab items still need billing at that point, they'll be
        # picked up by a manual re-run of this signal (or a nightly task).
        return

    # Also stamp completed_at timestamp
    if not instance.completed_at:
        instance.completed_at = timezone.now()
        # Save without re-triggering the signal (use qs update)
        type(instance).objects.filter(pk=instance.pk).update(
            completed_at=instance.completed_at,
        )

    # Iterate items — skip already-billed
    for item in instance.items.filter(is_billed=False):
        try:
            bill.system_add_item(
                service=item.service,
                quantity=1,
                unit_price=item.unit_price,
                description=f"Lab: {item.service.name} ({instance.order_number})",
            )
        except ValidationError:
            # Bill is CANCELLED / CLOSED — silently skip.
            continue

        # Mark billed
        type(item).objects.filter(pk=item.pk).update(is_billed=True)
