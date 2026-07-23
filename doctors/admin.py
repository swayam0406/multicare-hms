"""Admin configuration for the doctors app."""

from django.contrib import admin

from .models import Department, Doctor, DoctorAvailability


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin for hospital departments."""

    list_display = ("name", "code", "doctor_count", "is_active", "created_at")
    list_display_links = ("name", "code")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("name", "code", "description", "is_active")}),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["activate", "deactivate"]

    @admin.display(description="Doctors")
    def doctor_count(self, obj):
        return obj.doctors.count()

    @admin.action(description="Activate selected departments")
    def activate(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} department(s) activated.")

    @admin.action(description="Deactivate selected departments")
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} department(s) deactivated.")


class DoctorAvailabilityInline(admin.TabularInline):
    """Inline editor for a doctor's weekly availability."""

    model = DoctorAvailability
    extra = 1
    ordering = ("weekday", "start_time")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    """Admin for doctor profiles."""

    list_display = (
        "display_name",
        "department",
        "specialty",
        "consultation_fee",
        "is_available_for_booking",
        "created_at",
    )
    list_display_links = ("display_name",)
    list_filter = (
        "department",
        "is_available_for_booking",
        "years_of_experience",
    )
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
        "user__email",
        "license_number",
        "specialty",
    )
    ordering = ("user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [DoctorAvailabilityInline]

    fieldsets = (
        (None, {"fields": ("user", "department", "is_available_for_booking")}),
        (
            "Professional Details",
            {
                "fields": (
                    "license_number",
                    "specialty",
                    "qualifications",
                    "years_of_experience",
                    "bio",
                ),
            },
        ),
        (
            "Consultation",
            {
                "fields": ("consultation_fee", "consultation_duration_minutes"),
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

    @admin.display(description="Doctor", ordering="user__first_name")
    def display_name(self, obj):
        return obj.display_name


@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    """Admin for individual availability slots (usually edited via Doctor inline)."""

    list_display = ("doctor", "get_weekday_display", "start_time", "end_time")
    list_filter = ("weekday", "doctor__department")
    search_fields = ("doctor__user__first_name", "doctor__user__last_name")
    ordering = ("doctor", "weekday", "start_time")
    autocomplete_fields = ("doctor",)

    @admin.display(description="Weekday", ordering="weekday")
    def get_weekday_display(self, obj):
        return obj.get_weekday_display()
