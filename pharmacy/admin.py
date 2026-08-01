"""Admin configuration for the pharmacy app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import Dispense, DispenseItem, InventoryItem, StockMovement

MOVEMENT_COLORS = {
    "RECEIVE": ("#d1e7dd", "#0f5132"),
    "DISPENSE": ("#cfe2ff", "#0a58ca"),
    "ADJUST": ("#fff3cd", "#664d03"),
    "EXPIRE": ("#f8d7da", "#842029"),
    "TRANSFER": ("#e9ecef", "#495057"),
}

DISPENSE_STATUS_COLORS = {
    "PENDING": ("#fff3cd", "#664d03"),
    "DISPENSED": ("#d1e7dd", "#0f5132"),
    "CANCELLED": ("#f8d7da", "#842029"),
}


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    fields = (
        "movement_type",
        "quantity",
        "balance_after",
        "reason",
        "reference",
        "performed_by",
        "performed_at",
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = False
    ordering = ("-performed_at",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "medication_name",
        "quantity_on_hand",
        "reorder_threshold",
        "low_stock_badge",
        "unit_cost",
        "unit_sale_price",
        "last_restocked_at",
    )
    list_display_links = ("medication_name",)
    list_filter = ("last_restocked_at",)
    search_fields = ("medication__name",)
    autocomplete_fields = ("medication",)
    readonly_fields = ("last_restocked_at", "created_at", "updated_at")
    inlines = [StockMovementInline]
    ordering = ("medication__name",)

    fieldsets = (
        (None, {"fields": ("medication",)}),
        ("Stock", {"fields": ("quantity_on_hand", "reorder_threshold")}),
        ("Pricing", {"fields": ("unit_cost", "unit_sale_price")}),
        ("Notes", {"fields": ("notes", "last_restocked_at")}),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Medication", ordering="medication__name")
    def medication_name(self, obj):
        return obj.medication.name

    @admin.display(description="Status")
    def low_stock_badge(self, obj):
        if obj.is_low_stock:
            return format_html(
                '<span style="background:#f8d7da;color:#842029;'
                'padding:2px 8px;border-radius:4px;font-weight:600;">Low</span>'
            )
        return format_html(
            '<span style="background:#d1e7dd;color:#0f5132;'
            'padding:2px 8px;border-radius:4px;font-weight:600;">OK</span>'
        )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "inventory_item",
        "type_badge",
        "quantity",
        "balance_after",
        "performed_by",
        "performed_at",
    )
    list_filter = ("movement_type", "performed_at")
    search_fields = (
        "inventory_item__medication__name",
        "reason",
        "reference",
    )
    autocomplete_fields = ("inventory_item", "performed_by")
    readonly_fields = (
        "inventory_item",
        "movement_type",
        "quantity",
        "balance_after",
        "reason",
        "reference",
        "performed_by",
        "performed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Type")
    def type_badge(self, obj):
        bg, fg = MOVEMENT_COLORS.get(obj.movement_type, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_movement_type_display(),
        )


class DispenseItemInline(admin.TabularInline):
    model = DispenseItem
    extra = 1
    autocomplete_fields = (
        "prescription_item",
        "inventory_item",
    )
    fields = (
        "prescription_item",
        "inventory_item",
        "quantity_dispensed",
        "unit_price",
        "line_total",
        "is_billed",
    )
    readonly_fields = ("line_total", "is_billed")


@admin.register(Dispense)
class DispenseAdmin(admin.ModelAdmin):
    list_display = (
        "dispense_number",
        "patient_short",
        "status_badge",
        "item_count",
        "created_at",
    )
    list_display_links = ("dispense_number",)
    list_filter = ("status", "created_at")
    search_fields = (
        "dispense_number",
        "patient__first_name",
        "patient__last_name",
        "patient__patient_id",
    )
    autocomplete_fields = ("prescription", "patient", "dispensed_by")
    readonly_fields = (
        "dispense_number",
        "dispensed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    inlines = [DispenseItemInline]
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("dispense_number", "prescription", "patient", "status"),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        (
            "Cancellation",
            {
                "fields": ("cancelled_reason",),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "dispensed_by",
                    "dispensed_at",
                    "cancelled_at",
                    "created_at",
                    "updated_at",
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
        bg, fg = DISPENSE_STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


@admin.register(DispenseItem)
class DispenseItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "dispense",
        "inventory_item",
        "quantity_dispensed",
        "line_total",
        "is_billed",
    )
    search_fields = (
        "dispense__dispense_number",
        "inventory_item__medication__name",
    )
    autocomplete_fields = (
        "dispense",
        "prescription_item",
        "inventory_item",
    )
    readonly_fields = ("line_total", "is_billed")
