"""Admin configuration for the appointments app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Appointment

STATUS_COLORS = {
    "SCHEDULED": ("#e9ecef", "#495057"),
    "CONFIRMED": ("#cfe2ff", "#0a58ca"),
    "IN_PROGRESS": ("#cff4fc", "#055160"),
    "COMPLETED": ("#d1e7dd", "#0f5132"),
    "CANCELLED": ("#fff3cd", "#664d03"),
    "NO_SHOW": ("#f8d7da", "#842029"),
}


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """Custom admin for appointments."""

    list_display = (
        "id",
        "scheduled_start",
        "patient_link",
        "doctor_link",
        "reason_short",
        "status_badge",
        "booked_by",
    )
    list_display_links = ("id", "scheduled_start")
    list_filter = (
        "status",
        "doctor",
        "doctor__department",
        "scheduled_start",
    )
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "patient__patient_id",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "reason",
    )
    autocomplete_fields = ("patient", "doctor", "booked_by")
    ordering = ("-scheduled_start",)
    date_hierarchy = "scheduled_start"
    list_per_page = 25
    readonly_fields = ("scheduled_end", "created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "fields": ("patient", "doctor", "status"),
            },
        ),
        (
            _("Scheduling"),
            {
                "fields": ("scheduled_start", "scheduled_end"),
            },
        ),
        (
            _("Clinical"),
            {
                "fields": ("reason", "notes"),
            },
        ),
        (
            _("Cancellation"),
            {
                "fields": ("cancelled_reason",),
                "classes": ("collapse",),
            },
        ),
        (
            _("Audit"),
            {
                "fields": ("booked_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = [
        "mark_confirmed",
        "mark_cancelled",
        "mark_no_show",
    ]

    # ---------- Custom columns ----------

    @admin.display(description="Patient", ordering="patient__last_name")
    def patient_link(self, obj):
        return f"{obj.patient.full_name} ({obj.patient.patient_id})"

    @admin.display(description="Doctor", ordering="doctor__user__first_name")
    def doctor_link(self, obj):
        return obj.doctor.display_name

    @admin.display(description="Reason", ordering="reason")
    def reason_short(self, obj):
        return (obj.reason[:40] + "…") if len(obj.reason) > 40 else obj.reason

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        bg, fg = STATUS_COLORS.get(obj.status, ("#e9ecef", "#495057"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    # ---------- Bulk actions ----------

    @admin.action(description="Mark selected as Confirmed (from Scheduled)")
    def mark_confirmed(self, request, queryset):
        # Only Scheduled → Confirmed is a valid transition
        eligible = queryset.filter(status="SCHEDULED")
        skipped = queryset.count() - eligible.count()
        updated = eligible.update(status="CONFIRMED")
        self.message_user(
            request,
            f"{updated} confirmed. {skipped} skipped (not in Scheduled state).",
        )

    @admin.action(description="Mark selected as Cancelled")
    def mark_cancelled(self, request, queryset):
        # Any non-terminal → Cancelled
        eligible = queryset.exclude(status__in=("COMPLETED", "CANCELLED", "NO_SHOW"))
        skipped = queryset.count() - eligible.count()
        updated = eligible.update(
            status="CANCELLED",
            cancelled_reason="Bulk cancelled via admin",
        )
        self.message_user(
            request,
            f"{updated} cancelled. {skipped} skipped (already in a terminal state).",
        )

    @admin.action(description="Mark selected as No-show (from Scheduled/Confirmed)")
    def mark_no_show(self, request, queryset):
        eligible = queryset.filter(status__in=("SCHEDULED", "CONFIRMED"))
        skipped = queryset.count() - eligible.count()
        updated = eligible.update(status="NO_SHOW")
        self.message_user(
            request,
            f"{updated} marked no-show. {skipped} skipped.",
        )
