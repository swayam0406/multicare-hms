"""Models for the laboratory app."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction


class LabTestProfile(models.Model):
    """Lab-specific metadata attached to a ServiceCatalog entry."""

    class SampleType(models.TextChoices):
        BLOOD = "BLOOD", "Blood"
        URINE = "URINE", "Urine"
        STOOL = "STOOL", "Stool"
        SWAB = "SWAB", "Swab"
        OTHER = "OTHER", "Other"

    service = models.OneToOneField(
        "billing.ServiceCatalog",
        on_delete=models.CASCADE,
        related_name="lab_profile",
    )
    sample_type = models.CharField(
        max_length=10,
        choices=SampleType.choices,
        default=SampleType.BLOOD,
    )
    unit = models.CharField(max_length=20, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    turnaround_hours = models.PositiveSmallIntegerField(default=24)
    preparation_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "laboratory_test_profile"
        verbose_name = "Lab test profile"
        verbose_name_plural = "Lab test profiles"
        ordering = ["service__code"]

    def __str__(self):
        return f"{self.service.code} — {self.get_sample_type_display()}"

    @property
    def name(self) -> str:
        return self.service.name

    @property
    def code(self) -> str:
        return self.service.code


class LabOrder(models.Model):
    """
    A doctor's request for one or more lab tests.
    Attached to a MedicalRecord (the clinical anchor).
    """

    class Status(models.TextChoices):
        ORDERED = "ORDERED", "Ordered"
        SAMPLE_COLLECTED = "SAMPLE_COLLECTED", "Sample Collected"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    order_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated: LAB-YYYY-NNNNN.",
    )
    medical_record = models.ForeignKey(
        "medical_records.MedicalRecord",
        on_delete=models.PROTECT,
        related_name="lab_orders",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="lab_orders",
        help_text="Denormalized from medical_record.appointment.patient.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ORDERED,
    )
    clinical_notes = models.TextField(
        blank=True,
        help_text="Doctor's notes for the lab (e.g., 'Rule out dengue').",
    )

    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordered_lab_orders",
    )
    sample_collected_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "laboratory_lab_order"
        verbose_name = "Lab order"
        verbose_name_plural = "Lab orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.order_number} — {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_order_number() -> str:
        year = datetime.now().year
        prefix = f"LAB-{year}-"
        with transaction.atomic():
            last = (
                LabOrder.objects.select_for_update()
                .filter(order_number__startswith=prefix)
                .order_by("-order_number")
                .first()
            )
            if last:
                last_seq = int(last.order_number.split("-")[-1])
                next_seq = last_seq + 1
            else:
                next_seq = 1
        return f"{prefix}{next_seq:05d}"

    # ---------- State machine ----------

    ALLOWED_TRANSITIONS = {
        "ORDERED": {"SAMPLE_COLLECTED", "CANCELLED"},
        "SAMPLE_COLLECTED": {"IN_PROGRESS", "CANCELLED"},
        "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
    }

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def available_transitions(self) -> list[str]:
        return sorted(self.ALLOWED_TRANSITIONS.get(self.status, set()))

    @property
    def is_terminal(self) -> bool:
        return self.status in (self.Status.COMPLETED, self.Status.CANCELLED)


class LabOrderItem(models.Model):
    """
    A single test within a lab order.
    Result fields optional at creation — technician fills in later.
    """

    order = models.ForeignKey(
        LabOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    service = models.ForeignKey(
        "billing.ServiceCatalog",
        on_delete=models.PROTECT,
        related_name="lab_order_items",
        limit_choices_to={"is_active": True, "category": "LABORATORY"},
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshot of price at order time.",
    )

    # ---------- Result fields (filled by technician) ----------
    result_value = models.CharField(
        max_length=100,
        blank=True,
        help_text="Measured value (e.g., '5.4', 'Negative').",
    )
    result_unit = models.CharField(
        max_length=20,
        blank=True,
        help_text="Unit (auto-copied from lab profile).",
    )
    reference_range = models.CharField(
        max_length=100,
        blank=True,
        help_text="Normal range (auto-copied from lab profile).",
    )
    is_abnormal = models.BooleanField(default=False)
    result_notes = models.TextField(blank=True)

    resulted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resulted_lab_items",
    )
    resulted_at = models.DateTimeField(null=True, blank=True)

    # Billing idempotency flag
    is_billed = models.BooleanField(
        default=False,
        help_text="True once this item has been appended to the visit's bill.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "laboratory_lab_order_item"
        verbose_name = "Lab order item"
        verbose_name_plural = "Lab order items"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["is_billed"]),
        ]

    def __str__(self):
        return f"{self.service.code} — {self.result_display}"

    @property
    def result_display(self) -> str:
        if not self.result_value:
            return "Pending"
        parts = [self.result_value]
        if self.result_unit:
            parts.append(self.result_unit)
        return " ".join(parts)

    def save(self, *args, **kwargs):
        # Snapshot unit_price from service if not set
        if self.unit_price is None or self.unit_price == Decimal("0.00"):
            if self.service:
                self.unit_price = self.service.default_price

        # Auto-copy result_unit + reference_range from lab profile if missing
        if not self.result_unit and self.service_id:
            profile = getattr(self.service, "lab_profile", None)
            if profile:
                if not self.result_unit:
                    self.result_unit = profile.unit
                if not self.reference_range:
                    self.reference_range = profile.reference_range

        super().save(*args, **kwargs)
