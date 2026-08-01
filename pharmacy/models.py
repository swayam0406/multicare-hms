"""Models for the pharmacy app."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


class InventoryItem(models.Model):
    """Stock tracker for a MedicationCatalog entry."""

    medication = models.OneToOneField(
        "medical_records.MedicationCatalog",
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    quantity_on_hand = models.PositiveIntegerField(
        default=0,
        help_text="Current stock (in dispensing units: tablets, vials, etc.).",
    )
    reorder_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Trigger a low-stock alert when quantity_on_hand ≤ this.",
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Purchase cost per unit.",
    )
    unit_sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Sale price billed to the patient per unit.",
    )
    last_restocked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pharmacy_inventory_item"
        verbose_name = "Inventory item"
        verbose_name_plural = "Inventory items"
        ordering = ["medication__name"]
        indexes = [
            models.Index(fields=["quantity_on_hand"]),
        ]

    def __str__(self):
        return f"{self.medication.name} — {self.quantity_on_hand} in stock"

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_on_hand <= self.reorder_threshold

    @property
    def name(self) -> str:
        return self.medication.name

    def apply_movement(
        self,
        movement_type: str,
        quantity: int,
        performed_by=None,
        reason: str = "",
        reference: str = "",
    ) -> "StockMovement":
        """Atomically mutate stock and log a StockMovement."""
        from django.utils import timezone

        if quantity == 0:
            raise ValidationError("Movement quantity cannot be zero.")

        with transaction.atomic():
            locked = InventoryItem.objects.select_for_update().get(pk=self.pk)
            new_balance = locked.quantity_on_hand + quantity
            if new_balance < 0:
                raise ValidationError(
                    f"Insufficient stock: have {locked.quantity_on_hand}, "
                    f"trying to remove {-quantity}."
                )

            locked.quantity_on_hand = new_balance
            if quantity > 0 and movement_type == StockMovement.MovementType.RECEIVE:
                locked.last_restocked_at = timezone.now()
            locked.save(
                update_fields=[
                    "quantity_on_hand",
                    "last_restocked_at",
                    "updated_at",
                ]
            )

            movement = StockMovement.objects.create(
                inventory_item=locked,
                movement_type=movement_type,
                quantity=quantity,
                balance_after=new_balance,
                reason=reason,
                reference=reference,
                performed_by=performed_by,
            )

            self.quantity_on_hand = new_balance
            self.last_restocked_at = locked.last_restocked_at

        return movement


class StockMovement(models.Model):
    """Immutable audit log for every inventory change."""

    class MovementType(models.TextChoices):
        RECEIVE = "RECEIVE", "Received (purchase)"
        DISPENSE = "DISPENSE", "Dispensed"
        ADJUST = "ADJUST", "Adjustment"
        EXPIRE = "EXPIRE", "Expired / Damaged"
        TRANSFER = "TRANSFER", "Transferred"

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    movement_type = models.CharField(
        max_length=15,
        choices=MovementType.choices,
    )
    quantity = models.IntegerField(
        help_text="Signed: positive = added to stock, negative = removed.",
    )
    balance_after = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_stock_movement"
        verbose_name = "Stock movement"
        verbose_name_plural = "Stock movements"
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["inventory_item"]),
            models.Index(fields=["-performed_at"]),
            models.Index(fields=["movement_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0),
                name="stock_movement_quantity_nonzero",
            ),
        ]

    def __str__(self):
        sign = "+" if self.quantity > 0 else ""
        return (
            f"{self.get_movement_type_display()} "
            f"{sign}{self.quantity} on {self.inventory_item.medication.name}"
        )

    def clean(self):
        super().clean()
        if self.pk:
            original = StockMovement.objects.filter(pk=self.pk).first()
            if original:
                for field in (
                    "inventory_item_id",
                    "movement_type",
                    "quantity",
                    "balance_after",
                ):
                    if getattr(self, field) != getattr(original, field):
                        raise ValidationError(
                            f"Stock movements are immutable. Cannot change '{field}'."
                        )

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements cannot be deleted for audit reasons.")


class Dispense(models.Model):
    """
    A pharmacist's fulfillment of (part of) a prescription.
    Multiple dispenses per prescription allowed (partial fills / refills).

    Lifecycle:
      PENDING → DISPENSED (drawdown happens here)
              → CANCELLED (no drawdown)
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        DISPENSED = "DISPENSED", "Dispensed"
        CANCELLED = "CANCELLED", "Cancelled"

    dispense_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated: DSP-YYYY-NNNNN.",
    )
    prescription = models.ForeignKey(
        "medical_records.Prescription",
        on_delete=models.PROTECT,
        related_name="dispenses",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="dispenses",
        help_text="Denormalized from prescription.medical_record.appointment.patient.",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)

    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispensed_records",
    )
    dispensed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pharmacy_dispense"
        verbose_name = "Dispense"
        verbose_name_plural = "Dispenses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.dispense_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.dispense_number:
            self.dispense_number = self._generate_dispense_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_dispense_number() -> str:
        year = datetime.now().year
        prefix = f"DSP-{year}-"
        with transaction.atomic():
            last = (
                Dispense.objects.select_for_update()
                .filter(dispense_number__startswith=prefix)
                .order_by("-dispense_number")
                .first()
            )
            if last:
                last_seq = int(last.dispense_number.split("-")[-1])
                next_seq = last_seq + 1
            else:
                next_seq = 1
        return f"{prefix}{next_seq:05d}"

    # ---------- State machine ----------

    @property
    def is_terminal(self) -> bool:
        return self.status in (self.Status.DISPENSED, self.Status.CANCELLED)

    def mark_dispensed(self, user=None):
        """
        Move PENDING → DISPENSED with atomic inventory drawdown.

        Every DispenseItem draws its quantity from its inventory_item.
        Any insufficient-stock error rolls back the entire dispense.
        """
        from django.utils import timezone

        if self.status != self.Status.PENDING:
            raise ValidationError(
                f"Only pending dispenses can be marked dispensed "
                f"(current: {self.get_status_display()})."
            )
        if not self.items.exists():
            raise ValidationError("Cannot dispense with no items.")

        with transaction.atomic():
            for item in self.items.select_related("inventory_item").all():
                item.inventory_item.apply_movement(
                    movement_type=StockMovement.MovementType.DISPENSE,
                    quantity=-item.quantity_dispensed,
                    performed_by=user,
                    reference=self.dispense_number,
                )

            self.status = self.Status.DISPENSED
            self.dispensed_at = timezone.now()
            self.dispensed_by = user
            self.save()

    def mark_cancelled(self, reason: str, user=None):
        """Move PENDING → CANCELLED. No inventory drawdown."""
        from django.utils import timezone

        if self.status != self.Status.PENDING:
            raise ValidationError(
                f"Only pending dispenses can be cancelled "
                f"(current: {self.get_status_display()})."
            )
        if not reason:
            raise ValidationError("A cancellation reason is required.")

        self.status = self.Status.CANCELLED
        self.cancelled_reason = reason
        self.cancelled_at = timezone.now()
        self.save()


class DispenseItem(models.Model):
    """A single line drawn from a specific inventory item."""

    dispense = models.ForeignKey(
        Dispense,
        on_delete=models.CASCADE,
        related_name="items",
    )
    prescription_item = models.ForeignKey(
        "medical_records.PrescriptionItem",
        on_delete=models.PROTECT,
        related_name="dispense_items",
    )
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="dispense_items",
    )
    quantity_dispensed = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshot of unit_sale_price at dispense time.",
    )
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )
    is_billed = models.BooleanField(
        default=False,
        help_text="True once this item has been appended to the visit's bill.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_dispense_item"
        verbose_name = "Dispense item"
        verbose_name_plural = "Dispense items"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["dispense"]),
            models.Index(fields=["is_billed"]),
        ]

    def __str__(self):
        return f"{self.inventory_item.medication.name} × {self.quantity_dispensed}"

    def save(self, *args, **kwargs):
        # Snapshot unit_price from inventory if not set
        if (
            self.unit_price is None or self.unit_price == Decimal("0.00")
        ) and self.inventory_item_id:
            self.unit_price = self.inventory_item.unit_sale_price

        self.line_total = self.unit_price * self.quantity_dispensed
        super().save(*args, **kwargs)
