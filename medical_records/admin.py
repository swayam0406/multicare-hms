"""Admin configuration for the medical_records app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ConditionCatalog,
    Diagnosis,
    MedicalRecord,
    MedicationCatalog,
    Prescription,
    PrescriptionItem,
    Vitals,
)


@admin.register(ConditionCatalog)
class ConditionCatalogAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_active", "created_at")
    list_display_links = ("code", "name")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name")
    ordering = ("code",)
    list_per_page = 50
    readonly_fields = ("created_at",)


@admin.register(MedicationCatalog)
class MedicationCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "strength", "form", "manufacturer", "is_active", "created_at")
    list_display_links = ("name",)
    list_filter = ("form", "is_active")
    search_fields = ("name", "strength", "manufacturer")
    ordering = ("name", "strength")
    list_per_page = 50
    readonly_fields = ("created_at",)


class VitalsInline(admin.StackedInline):
    model = Vitals
    can_delete = True
    autocomplete_fields = ("recorded_by",)
    readonly_fields = ("recorded_at", "bp_display", "bmi_display")
    fieldsets = (
        (
            "Blood Pressure",
            {
                "fields": (("bp_systolic", "bp_diastolic"), "bp_display"),
            },
        ),
        (
            "Cardiovascular / Respiratory",
            {
                "fields": ("pulse", "respiratory_rate", "spo2"),
            },
        ),
        (
            "Temperature",
            {
                "fields": ("temperature",),
            },
        ),
        (
            "Anthropometrics",
            {
                "fields": (("weight_kg", "height_cm"), "bmi_display"),
            },
        ),
        (
            "Audit",
            {
                "fields": ("recorded_by", "recorded_at"),
            },
        ),
    )

    @admin.display(description="BP")
    def bp_display(self, obj):
        return obj.bp or "—"

    @admin.display(description="BMI")
    def bmi_display(self, obj):
        bmi = obj.bmi
        if bmi is None:
            return "—"
        return f"{bmi} ({obj.bmi_category})"


class DiagnosisInline(admin.TabularInline):
    model = Diagnosis
    extra = 1
    autocomplete_fields = ("condition",)
    fields = ("condition", "is_primary", "notes")


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 1
    autocomplete_fields = ("medication",)
    fields = ("order", "medication", "dose", "frequency", "duration_days", "instructions")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "medical_record", "item_count", "valid_until", "created_at")
    search_fields = (
        "medical_record__appointment__patient__first_name",
        "medical_record__appointment__patient__last_name",
        "medical_record__appointment__patient__patient_id",
    )
    autocomplete_fields = ("medical_record",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [PrescriptionItemInline]

    fieldsets = (
        (
            None,
            {
                "fields": ("medical_record", "valid_until", "follow_up_after_days"),
            },
        ),
        (
            "Instructions",
            {
                "fields": ("general_instructions",),
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


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ("id", "prescription", "medication", "dose", "frequency", "duration_days")
    list_filter = ("frequency",)
    search_fields = ("medication__name",)
    autocomplete_fields = ("prescription", "medication")


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "appointment",
        "chief_complaint_short",
        "primary_dx_short",
        "diagnosis_summary",
        "has_prescription",
        "lock_badge",
        "created_at",
    )
    list_filter = ("is_locked", "created_at")
    search_fields = (
        "appointment__patient__first_name",
        "appointment__patient__last_name",
        "appointment__patient__patient_id",
        "chief_complaint",
    )
    autocomplete_fields = ("appointment", "created_by")
    ordering = ("-created_at",)
    readonly_fields = ("locked_at", "created_at", "updated_at")
    inlines = [VitalsInline, DiagnosisInline]

    fieldsets = (
        (
            None,
            {
                "fields": ("appointment", "created_by", ("is_locked", "locked_at")),
            },
        ),
        (
            "Presentation",
            {
                "fields": ("chief_complaint", "history_present_illness"),
            },
        ),
        (
            "Examination",
            {
                "fields": ("examination_findings",),
            },
        ),
        (
            "Clinical Notes (patient-visible)",
            {
                "fields": ("clinical_notes",),
            },
        ),
        (
            "Doctor's Private Notes",
            {
                "fields": ("private_notes",),
                "description": "Never shown to the patient.",
                "classes": ("collapse",),
            },
        ),
        (
            "Follow-up",
            {
                "fields": ("follow_up_recommendation",),
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

    @admin.display(description="Chief complaint")
    def chief_complaint_short(self, obj):
        if not obj.chief_complaint:
            return "—"
        return (
            (obj.chief_complaint[:40] + "…")
            if len(obj.chief_complaint) > 40
            else obj.chief_complaint
        )

    @admin.display(description="Primary Dx")
    def primary_dx_short(self, obj):
        pd = obj.primary_diagnosis
        if pd is None:
            return "—"
        return pd.condition.code

    @admin.display(description="Diagnoses")
    def diagnosis_summary(self, obj):
        codes = obj.diagnoses.values_list("condition__code", flat=True)
        return ", ".join(codes) if codes else "—"

    @admin.display(description="Rx", boolean=True)
    def has_prescription(self, obj):
        return hasattr(obj, "prescription")

    @admin.display(description="Lock")
    def lock_badge(self, obj):
        if obj.is_locked:
            return format_html(
                '<span style="background:#f8d7da;color:#842029;'
                'padding:2px 8px;border-radius:4px;">🔒 Locked</span>'
            )
        return format_html(
            '<span style="background:#d1e7dd;color:#0f5132;'
            'padding:2px 8px;border-radius:4px;">Open</span>'
        )


@admin.register(Vitals)
class VitalsAdmin(admin.ModelAdmin):
    """Standalone Vitals admin (usually edited via inline)."""

    list_display = (
        "id",
        "medical_record",
        "bp_display",
        "pulse",
        "temperature",
        "bmi_display",
        "recorded_at",
    )
    search_fields = (
        "medical_record__appointment__patient__first_name",
        "medical_record__appointment__patient__last_name",
    )
    autocomplete_fields = ("medical_record", "recorded_by")
    readonly_fields = ("recorded_at",)

    @admin.display(description="BP")
    def bp_display(self, obj):
        return obj.bp or "—"

    @admin.display(description="BMI")
    def bmi_display(self, obj):
        return obj.bmi or "—"


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ("id", "medical_record", "condition", "is_primary", "created_at")
    list_filter = ("is_primary", "condition__category")
    search_fields = (
        "condition__code",
        "condition__name",
        "medical_record__appointment__patient__first_name",
        "medical_record__appointment__patient__last_name",
    )
    autocomplete_fields = ("medical_record", "condition")
    readonly_fields = ("created_at",)
