"""Admin configuration for the laboratory app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import LabOrder, LabOrderItem, LabTestProfile

ORDER_STATUS_COLORS = {
    "ORDERED": ("#cfe2ff", "#0a58ca"),
    "SAMPLE_COLLECTED": ("#fff3cd", "#664d03"),
    "IN_PROGRESS": ("#cff4fc", "#055160"),
    "COMPLETED": ("#d1e7dd", "#0f5132"),
    "CANCELLED": ("#f8d7da", "#842029"),
}


@admin.register(LabTestProfile)
class LabTestProfileAdmin(admin.ModelAdmin):
    list_display = (
        "code_display",
        "name_display",
        "sample_type",
        "unit",
        "reference_range",
        "turnaround_hours",
    )
    list_display_links = ("code_display", "name_display")
    list_filter = ("sample_type",)
    search_fields = ("service__code", "service__name")
    autocomplete_fields = ("service",)
    ordering = ("service__code",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("service",)}),
        (
            "Sample & Result",
            {
                "fields": ("sample_type", "unit", "reference_range"),
            },
        ),
        (
            "Logistics",
            {
                "fields": ("turnaround_hours", "preparation_notes"),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Code", ordering="service__code")
    def code_display(self, obj):
        return obj.service.code

    @admin.display(description="Name", ordering="service__name")
    def name_display(self, obj):
        return obj.service.name


class LabOrderItemInline(admin.TabularInline):
    model = LabOrderItem
    extra = 1
    autocomplete_fields = ("service",)
    fields = (
        "service",
        "unit_price",
        "result_value",
        "result_unit",
        "reference_range",
        "is_abnormal",
        "is_billed",
    )
    readonly_fields = ("is_billed",)


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "patient_short",
        "status_badge",
        "item_count",
        "created_at",
    )
    list_display_links = ("order_number",)
    list_filter = ("status", "created_at")
    search_fields = (
        "order_number",
        "patient__first_name",
        "patient__last_name",
        "patient__patient_id",
    )
    autocomplete_fields = ("medical_record", "patient", "ordered_by")
    readonly_fields = (
        "order_number",
        "sample_collected_at",
        "completed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    inlines = [LabOrderItemInline]
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("order_number", "medical_record", "patient", "status"),
            },
        ),
        (
            "Clinical",
            {
                "fields": ("clinical_notes",),
            },
        ),
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
                    "ordered_by",
                    "sample_collected_at",
                    "completed_at",
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
        bg, fg = ORDER_STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
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


@admin.register(LabOrderItem)
class LabOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "service",
        "result_display",
        "is_abnormal",
        "is_billed",
    )
    list_filter = ("is_abnormal", "is_billed")
    search_fields = ("order__order_number", "service__name")
    autocomplete_fields = ("order", "service", "resulted_by")
    readonly_fields = ("is_billed",)

    @admin.display(description="Result")
    def result_display(self, obj):
        return obj.result_display
