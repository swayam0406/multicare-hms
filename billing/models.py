"""Models for the billing app."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


class ServiceCatalog(models.Model):
    """Curated catalog of chargeable services."""

    class Category(models.TextChoices):
        CONSULTATION = "CONSULTATION", "Consultation"
        LABORATORY = "LABORATORY", "Laboratory"
        IMAGING = "IMAGING", "Imaging"
        PROCEDURE = "PROCEDURE", "Procedure"
        ROOM = "ROOM", "Room / Ward"
        OTHER = "OTHER", "Other"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    default_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_taxable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_service_catalog"
        verbose_name = "Service (catalog)"
        verbose_name_plural = "Services (catalog)"
        ordering = ["category", "code"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.name} (₹{self.default_price})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().strip()
        super().save(*args, **kwargs)


class Bill(models.Model):
    """A bill for one appointment."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"
        PARTIAL = "PARTIAL", "Partially Paid"
        PAID = "PAID", "Paid"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    bill_number = models.CharField(max_length=20, unique=True, editable=False)
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.PROTECT,
        related_name="bill",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="bills",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bills",
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_bills",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_bill"
        verbose_name = "Bill"
        verbose_name_plural = "Bills"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.bill_number} — {self.patient.full_name} (₹{self.total})"

    def save(self, *args, **kwargs):
        if not self.bill_number:
            self.bill_number = self._generate_bill_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_bill_number() -> str:
        year = datetime.now().year
        prefix = f"INV-{year}-"
        with transaction.atomic():
            last = (
                Bill.objects.select_for_update()
                .filter(bill_number__startswith=prefix)
                .order_by("-bill_number")
                .first()
            )
            if last:
                last_seq = int(last.bill_number.split("-")[-1])
                next_seq = last_seq + 1
            else:
                next_seq = 1
        return f"{prefix}{next_seq:05d}"

    def recompute_totals(self, save: bool = True):
        subtotal = sum(
            (item.line_total for item in self.items.all()),
            Decimal("0.00"),
        )
        discounted = max(subtotal - self.discount_amount, Decimal("0.00"))
        tax = (discounted * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        total = discounted + tax

        self.subtotal = subtotal
        self.tax_amount = tax
        self.total = total

        if save:
            self.save(
                update_fields=[
                    "subtotal",
                    "tax_amount",
                    "total",
                    "updated_at",
                ]
            )
        return total

    @property
    def paid_amount(self) -> Decimal:
        """
        Sum of net completed payments (payment.amount - sum of its refunds).
        Uses net_amount to correctly reflect partial refunds.
        """
        total = Decimal("0.00")
        for payment in self.payments.filter(status="COMPLETED"):
            total += payment.net_amount
        return total

    @property
    def balance(self) -> Decimal:
        return max(self.total - self.paid_amount, Decimal("0.00"))

    @property
    def is_fully_paid(self) -> bool:
        return self.balance <= Decimal("0.00") and self.total > Decimal("0.00")

    def can_edit_items(self) -> bool:
        return self.status == self.Status.DRAFT

    def accepts_payments(self) -> bool:
        return self.status in (
            self.Status.FINALIZED,
            self.Status.PARTIAL,
            self.Status.PAID,
        )

    def finalize(self, user=None):
        from django.utils import timezone

        if self.status != self.Status.DRAFT:
            raise ValidationError(
                f"Only draft bills can be finalized (current: {self.get_status_display()})."
            )
        if not self.items.exists():
            raise ValidationError("Cannot finalize a bill with no items.")

        self.recompute_totals(save=False)
        self.status = self.Status.FINALIZED
        self.finalized_at = timezone.now()
        self.finalized_by = user
        self.save()

    def refresh_status_after_payment(self):
        if self.status in (self.Status.CANCELLED, self.Status.CLOSED, self.Status.DRAFT):
            return
        if self.is_fully_paid:
            self.status = self.Status.PAID
        elif self.paid_amount > Decimal("0.00"):
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.FINALIZED
        self.save(update_fields=["status", "updated_at"])


class BillItem(models.Model):
    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name="items",
    )
    service = models.ForeignKey(
        ServiceCatalog,
        on_delete=models.PROTECT,
        related_name="bill_items",
        limit_choices_to={"is_active": True},
    )
    description = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_bill_item"
        verbose_name = "Bill item"
        verbose_name_plural = "Bill items"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="bill_item_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["bill"]),
        ]

    def __str__(self):
        return f"{self.display_name} × {self.quantity} = ₹{self.line_total}"

    @property
    def display_name(self) -> str:
        return self.description or self.service.name

    def save(self, *args, **kwargs):
        if self.unit_price is None or self.unit_price == Decimal("0.00"):
            if self.service:
                self.unit_price = self.service.default_price
        if not self.description and self.service:
            self.description = self.service.name

        self.line_total = self.unit_price * self.quantity

        super().save(*args, **kwargs)
        self.bill.recompute_totals()

    def delete(self, *args, **kwargs):
        bill = self.bill
        super().delete(*args, **kwargs)
        bill.recompute_totals()


class Payment(models.Model):
    """A payment received against a bill."""

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Credit/Debit Card"
        UPI = "UPI", "UPI"
        NETBANKING = "NETBANKING", "Net Banking"
        INSURANCE = "INSURANCE", "Insurance"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    bill = models.ForeignKey(
        Bill,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    method = models.CharField(
        max_length=15,
        choices=Method.choices,
        default=Method.CASH,
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments",
    )
    received_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payment"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-received_at", "-created_at"]
        indexes = [
            models.Index(fields=["bill"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-received_at"]),
        ]

    def __str__(self):
        return f"₹{self.amount} via {self.get_method_display()} — {self.get_status_display()}"

    @property
    def refunded_amount(self) -> Decimal:
        return self.refunds.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def net_amount(self) -> Decimal:
        """Payment amount minus any refunds."""
        return self.amount - self.refunded_amount

    def clean(self):
        super().clean()

        if self.pk:
            original = Payment.objects.filter(pk=self.pk).first()
            if original and original.status == Payment.Status.COMPLETED:
                allowed_status_change = (
                    self.status == Payment.Status.REFUNDED
                    and original.status == Payment.Status.COMPLETED
                )
                for field in ("amount", "method", "bill_id"):
                    if getattr(self, field) != getattr(original, field):
                        raise ValidationError(
                            f"Completed payments are immutable. Cannot change '{field}'."
                        )
                if not allowed_status_change and self.status != original.status:
                    raise ValidationError(
                        "Completed payments cannot change status "
                        "(except to REFUNDED via a refund workflow)."
                    )

        if self.bill_id and not self.bill.accepts_payments():
            raise ValidationError(
                f"Payments can only be recorded against finalized bills "
                f"(current status: {self.bill.get_status_display()})."
            )

        if self.status == Payment.Status.COMPLETED and not self.pk:
            if self.amount > self.bill.balance:
                raise ValidationError(
                    f"Payment amount ₹{self.amount} exceeds outstanding balance "
                    f"₹{self.bill.balance}."
                )

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if not self.received_at:
            self.received_at = timezone.now()
        super().save(*args, **kwargs)
        self.bill.refresh_status_after_payment()

    def delete(self, *args, **kwargs):
        raise ValidationError("Payments cannot be deleted. Use a Refund to reverse a payment.")


class InsuranceClaim(models.Model):
    """Insurance claim against a bill."""

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAID = "PAID", "Paid"

    bill = models.ForeignKey(
        Bill,
        on_delete=models.PROTECT,
        related_name="insurance_claims",
    )
    provider = models.CharField(max_length=100)
    policy_number = models.CharField(max_length=50)
    claim_number = models.CharField(max_length=50, blank=True)

    amount_claimed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    amount_approved = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    linked_payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_claim",
    )

    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_insurance_claims",
    )

    class Meta:
        db_table = "billing_insurance_claim"
        verbose_name = "Insurance claim"
        verbose_name_plural = "Insurance claims"
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["bill"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.provider} claim — ₹{self.amount_claimed} " f"({self.get_status_display()})"

    def mark_approved(self, amount_approved: Decimal, user=None, notes: str = ""):
        from django.utils import timezone

        if self.status != self.Status.SUBMITTED:
            raise ValidationError(
                f"Only submitted claims can be approved (current: {self.get_status_display()})."
            )
        if amount_approved < Decimal("0.00"):
            raise ValidationError("Approved amount cannot be negative.")
        if amount_approved > self.amount_claimed:
            raise ValidationError(
                f"Approved amount ₹{amount_approved} exceeds claimed ₹{self.amount_claimed}."
            )

        self.status = self.Status.APPROVED
        self.amount_approved = amount_approved
        self.approved_at = timezone.now()
        if notes:
            self.notes = (self.notes + "\n\n" + notes).strip() if self.notes else notes
        self.save()

    def mark_rejected(self, reason: str, user=None):
        if self.status not in (self.Status.SUBMITTED, self.Status.APPROVED):
            raise ValidationError(f"Cannot reject a claim in {self.get_status_display()} state.")
        if not reason:
            raise ValidationError("A rejection reason is required.")

        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.amount_approved = Decimal("0.00")
        self.save()

    def mark_paid(self, received_by=None):
        from django.utils import timezone

        if self.status != self.Status.APPROVED:
            raise ValidationError(
                f"Only approved claims can be marked paid "
                f"(current: {self.get_status_display()})."
            )
        if self.amount_approved <= Decimal("0.00"):
            raise ValidationError("Cannot mark a claim with zero approved amount as paid.")

        if not self.linked_payment:
            payment_amount = min(self.amount_approved, self.bill.balance)
            if payment_amount <= Decimal("0.00"):
                raise ValidationError("Bill has no outstanding balance for insurance payment.")

            payment = Payment.objects.create(
                bill=self.bill,
                amount=payment_amount,
                method=Payment.Method.INSURANCE,
                status=Payment.Status.COMPLETED,
                reference=f"{self.provider} claim {self.claim_number or self.pk}",
                received_by=received_by,
                notes=f"Insurance payout for policy {self.policy_number}",
            )
            self.linked_payment = payment

        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save()


class Refund(models.Model):
    """
    An auditable reversal of a completed payment. Partial refunds supported.

    Rules:
      - Payment must be COMPLETED.
      - Total refunds cannot exceed the payment amount.
      - Refunds are immutable once created (like completed Payments).
      - Refunds cannot be deleted.
      - When cumulative refunds == payment.amount, the Payment flips to REFUNDED.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card reversal"
        UPI = "UPI", "UPI"
        NETBANKING = "NETBANKING", "Net Banking"
        INSURANCE = "INSURANCE", "Insurance write-off"

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Refund amount in INR.",
    )
    method = models.CharField(
        max_length=15,
        choices=Method.choices,
        default=Method.CASH,
        help_text="How the money was returned to the patient.",
    )
    reason = models.TextField(help_text="Why this refund was issued.")
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="External reference (bank ref, cheque number).",
    )
    notes = models.TextField(blank=True)

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_refunds",
    )
    processed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_refund"
        verbose_name = "Refund"
        verbose_name_plural = "Refunds"
        ordering = ["-processed_at", "-created_at"]
        indexes = [
            models.Index(fields=["payment"]),
            models.Index(fields=["-processed_at"]),
        ]

    def __str__(self):
        return f"Refund ₹{self.amount} of payment #{self.payment_id}"

    def clean(self):
        super().clean()

        # Immutability — refunds can't be edited after creation
        if self.pk:
            original = Refund.objects.filter(pk=self.pk).first()
            if original:
                for field in ("payment_id", "amount", "method"):
                    if getattr(self, field) != getattr(original, field):
                        raise ValidationError(f"Refunds are immutable. Cannot change '{field}'.")

        # Payment must be COMPLETED (not PENDING/FAILED/already-REFUNDED)
        if self.payment_id and self.payment.status != Payment.Status.COMPLETED:
            raise ValidationError(
                f"Refunds can only be issued against completed payments "
                f"(current: {self.payment.get_status_display()})."
            )

        # Reason required
        if not self.reason or not self.reason.strip():
            raise ValidationError("A refund reason is required.")

        # Total refunds can't exceed payment amount
        if self.payment_id and not self.pk:
            existing = self.payment.refunded_amount
            if existing + self.amount > self.payment.amount:
                raise ValidationError(
                    f"Cumulative refunds ₹{existing + self.amount} would exceed "
                    f"payment amount ₹{self.payment.amount}."
                )

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if not self.processed_at:
            self.processed_at = timezone.now()

        super().save(*args, **kwargs)

        # If cumulative refunds equal the payment amount, flip payment to REFUNDED
        # This uses queryset-level update to bypass the immutability clean().
        payment = self.payment
        if payment.refunded_amount >= payment.amount:
            Payment.objects.filter(pk=payment.pk).update(
                status=Payment.Status.REFUNDED,
            )

        # Update bill status (paid_amount uses net_amount, so it drops accordingly)
        payment.refresh_from_db()
        payment.bill.refresh_status_after_payment()

    def delete(self, *args, **kwargs):
        raise ValidationError("Refunds cannot be deleted for audit reasons.")
