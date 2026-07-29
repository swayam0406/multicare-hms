"""Admin configuration for the billing app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Bill,
    BillItem,
    InsuranceClaim,
    Payment,
    Refund,
    ServiceCatalog,
)

BILL_STATUS_COLORS = {
    "DRAFT": ("#e9ecef", "#495057"),
    "FINALIZED": ("#cfe2ff", "#0a58ca"),
    "PARTIAL": ("#fff3cd", "#664d03"),
    "PAID": ("#d1e7dd", "#0f5132"),
    "CLOSED": ("#e9ecef", "#495057"),
    "CANCELLED": ("#f8d7da", "#842029"),
}

PAYMENT_STATUS_COLORS = {
    "PENDING": ("#fff3cd", "#664d03"),
    "COMPLETED": ("#d1e7dd", "#0f5132"),
    "FAILED": ("#f8d7da", "#842029"),
    "REFUNDED": ("#e9ecef", "#495057"),
}

CLAIM_STATUS_COLORS = {
    "SUBMITTED": ("#cfe2ff", "#0a58ca"),
    "APPROVED": ("#fff3cd", "#664d03"),
    "REJECTED": ("#f8d7da", "#842029"),
    "PAID": ("#d1e7dd", "#0f5132"),
}


@admin.register(ServiceCatalog)
class ServiceCatalogAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "default_price",
        "is_taxable",
        "is_active",
        "created_at",
    )
    list_display_links = ("code", "name")
    list_filter = ("category", "is_taxable", "is_active")
    search_fields = ("code", "name")
    ordering = ("category", "code")
    list_per_page = 50
    readonly_fields = ("created_at",)


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 1
    autocomplete_fields = ("service",)
    fields = ("service", "description", "unit_price", "quantity", "line_total")
    readonly_fields = ("line_total",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = (
        "amount",
        "method",
        "status",
        "reference",
        "received_by",
        "received_at",
    )
    readonly_fields = ("received_at",)
    autocomplete_fields = ("received_by",)
    show_change_link = True


class InsuranceClaimInline(admin.TabularInline):
    model = InsuranceClaim
    extra = 0
    fields = (
        "provider",
        "policy_number",
        "amount_claimed",
        "amount_approved",
        "status",
    )
    show_change_link = True


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    fields = ("amount", "method", "reason", "processed_by", "processed_at")
    readonly_fields = ("processed_at",)
    autocomplete_fields = ("processed_by",)
    show_change_link = True


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    actions = ["close_paid_bills"]
    list_display = (
        "bill_number",
        "patient_short",
        "status_badge",
        "total",
        "paid_display",
        "balance_display",
        "created_at",
    )
    list_display_links = ("bill_number",)
    list_filter = ("status", "created_at")
    search_fields = (
        "bill_number",
        "patient__first_name",
        "patient__last_name",
        "patient__patient_id",
    )
    autocomplete_fields = ("appointment", "patient", "created_by", "finalized_by")
    readonly_fields = (
        "bill_number",
        "subtotal",
        "tax_amount",
        "total",
        "paid_display",
        "balance_display",
        "created_at",
        "updated_at",
        "finalized_at",
    )
    inlines = [BillItemInline, PaymentInline, InsuranceClaimInline]
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("bill_number", "appointment", "patient", "status"),
            },
        ),
        (
            "Money",
            {
                "fields": (
                    "subtotal",
                    ("discount_amount", "tax_rate"),
                    "tax_amount",
                    "total",
                    ("paid_display", "balance_display"),
                ),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        (
            "Audit",
            {
                "fields": (
                    "created_by",
                    "finalized_by",
                    "created_at",
                    "updated_at",
                    "finalized_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Patient", ordering="patient__last_name")
    def patient_short(self, obj):
        return f"{obj.patient.full_name} ({obj.patient.patient_id})"

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = BILL_STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Paid")
    def paid_display(self, obj):
        return f"₹{obj.paid_amount}"

    @admin.display(description="Balance")
    def balance_display(self, obj):
        return f"₹{obj.balance}"

    @admin.action(description="Close selected paid bills")
    def close_paid_bills(self, request, queryset):
        eligible = queryset.filter(status="PAID")
        updated = eligible.update(status="CLOSED")
        skipped = queryset.count() - updated
        self.message_user(
            request,
            f"{updated} bill(s) closed. {skipped} skipped (not in PAID state).",
        )


@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ("id", "bill", "service", "unit_price", "quantity", "line_total")
    search_fields = ("bill__bill_number", "service__name")
    autocomplete_fields = ("bill", "service")
    readonly_fields = ("line_total",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "bill",
        "amount",
        "method",
        "status_badge",
        "net_amount_display",
        "received_by",
        "received_at",
    )
    list_filter = ("status", "method", "received_at")
    search_fields = ("bill__bill_number", "reference")
    autocomplete_fields = ("bill", "received_by")
    readonly_fields = ("received_at", "created_at", "updated_at")
    ordering = ("-received_at",)
    inlines = [RefundInline]

    fieldsets = (
        (None, {"fields": ("bill", "amount", "method", "status")}),
        ("Details", {"fields": ("reference", "notes")}),
        (
            "Audit",
            {
                "fields": ("received_by", "received_at", "created_at", "updated_at"),
            },
        ),
    )

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == Payment.Status.COMPLETED:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = PAYMENT_STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Net")
    def net_amount_display(self, obj):
        if obj.refunded_amount > 0:
            return f"₹{obj.net_amount} (refunded ₹{obj.refunded_amount})"
        return f"₹{obj.amount}"


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "bill",
        "provider",
        "amount_claimed",
        "amount_approved",
        "status_badge",
        "submitted_at",
    )
    list_filter = ("status", "provider", "submitted_at")
    search_fields = (
        "bill__bill_number",
        "provider",
        "policy_number",
        "claim_number",
    )
    autocomplete_fields = ("bill", "linked_payment", "created_by")
    readonly_fields = (
        "submitted_at",
        "approved_at",
        "paid_at",
        "linked_payment",
    )
    ordering = ("-submitted_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("bill", "provider", "policy_number", "claim_number"),
            },
        ),
        ("Amounts", {"fields": ("amount_claimed", "amount_approved")}),
        ("Status", {"fields": ("status", "linked_payment")}),
        ("Notes", {"fields": ("notes", "rejection_reason")}),
        (
            "Audit",
            {
                "fields": (
                    "created_by",
                    "submitted_at",
                    "approved_at",
                    "paid_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = CLAIM_STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment",
        "amount",
        "method",
        "processed_by",
        "processed_at",
    )
    list_filter = ("method", "processed_at")
    search_fields = (
        "payment__bill__bill_number",
        "reason",
        "reference",
    )
    autocomplete_fields = ("payment", "processed_by")
    readonly_fields = ("processed_at", "created_at")
    ordering = ("-processed_at",)

    fieldsets = (
        (None, {"fields": ("payment", "amount", "method")}),
        ("Details", {"fields": ("reason", "reference", "notes")}),
        ("Audit", {"fields": ("processed_by", "processed_at", "created_at")}),
    )

    def has_change_permission(self, request, obj=None):
        # Immutable once created
        if obj:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
