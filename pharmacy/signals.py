"""Signals for the pharmacy app."""

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="pharmacy.Dispense")
def bill_dispense_on_completion(sender, instance, created, **kwargs):
    """
    When a Dispense moves to DISPENSED, append each unbilled item to the
    visit's bill via Bill.system_add_item.
    Idempotent — items with is_billed=True are skipped.
    """
    if created:
        return
    if instance.status != "DISPENSED":
        return

    from billing.models import Bill

    # Walk the chain: prescription → medical_record → appointment → bill
    medical_record = instance.prescription.medical_record
    appointment = medical_record.appointment
    bill = Bill.objects.filter(appointment=appointment).first()
    if bill is None:
        return  # No bill yet — appointment not completed. Skip.

    for item in instance.items.filter(is_billed=False).select_related(
        "inventory_item__medication",
    ):
        # Find or create a matching ServiceCatalog entry for the medication
        service = _get_or_create_medication_service(item.inventory_item)

        try:
            bill.system_add_item(
                service=service,
                quantity=item.quantity_dispensed,
                unit_price=item.unit_price,
                description=f"Pharmacy: {item.inventory_item.medication.name} ({instance.dispense_number})",
            )
        except ValidationError:
            # Bill CANCELLED / CLOSED — silently skip
            continue

        type(item).objects.filter(pk=item.pk).update(is_billed=True)


def _get_or_create_medication_service(inventory_item):
    """
    Ensure a ServiceCatalog entry exists for the medication.
    Uses a synthesized code prefixed with PHARMA-.
    """
    from billing.models import ServiceCatalog

    code = f"PHARMA-{inventory_item.medication_id:05d}"
    service, _ = ServiceCatalog.objects.get_or_create(
        code=code,
        defaults={
            "name": inventory_item.medication.name,
            "category": ServiceCatalog.Category.OTHER,
            "default_price": inventory_item.unit_sale_price,
            "is_active": True,
        },
    )
    return service
