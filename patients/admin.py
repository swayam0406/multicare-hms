"""Admin configuration for the patients app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    """Custom admin for the Patient model."""

    # ---------- List view ----------
    list_display = (
        'patient_id',
        'full_name_display',
        'age_display',
        'gender',
        'blood_group_badge',
        'phone',
        'is_active_badge',
        'created_at',
    )
    list_display_links = ('patient_id', 'full_name_display')
    list_filter = (
        'is_active',
        'gender',
        'blood_group',
        'marital_status',
        'created_at',
    )
    search_fields = (
        'patient_id',
        'first_name',
        'last_name',
        'phone',
        'email',
    )
    ordering = ('-created_at',)
    list_per_page = 25
    date_hierarchy = 'created_at'

    # ---------- Detail (change) view ----------
    readonly_fields = (
        'patient_id',
        'created_at',
        'updated_at',
        'age_display',
    )

    fieldsets = (
        (None, {
            'fields': ('patient_id', 'is_active'),
        }),
        (_('Portal Link'), {
            'fields': ('user',),
            'description': 'Optional link to a User account for portal access.',
        }),
        (_('Demographics'), {
            'fields': (
                'first_name',
                'last_name',
                'date_of_birth',
                'age_display',
                'gender',
                'blood_group',
                'marital_status',
            ),
        }),
        (_('Contact'), {
            'fields': (
                'phone',
                'email',
                'address_line',
                ('city', 'state', 'pincode'),
            ),
        }),
        (_('Emergency Contact'), {
            'fields': (
                'emergency_contact_name',
                'emergency_contact_phone',
                'emergency_contact_relation',
            ),
            'classes': ('collapse',),
        }),
        (_('Medical Basics'), {
            'fields': (
                'allergies',
                'chronic_conditions',
                'current_medications',
            ),
            'classes': ('collapse',),
        }),
        (_('Audit Trail'), {
            'fields': ('registered_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    autocomplete_fields = ('user', 'registered_by')

    # ---------- Bulk actions ----------
    actions = ['deactivate_patients', 'reactivate_patients']

    @admin.action(description='Deactivate selected patients')
    def deactivate_patients(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} patient(s) deactivated.')

    @admin.action(description='Reactivate selected patients')
    def reactivate_patients(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} patient(s) reactivated.')

    # ---------- Custom columns ----------
    @admin.display(description='Name', ordering='first_name')
    def full_name_display(self, obj):
        return obj.full_name

    @admin.display(description='Age', ordering='date_of_birth')
    def age_display(self, obj):
        try:
            return f'{obj.age} yrs'
        except (AttributeError, TypeError):
            return '—'

    @admin.display(description='Blood', ordering='blood_group')
    def blood_group_badge(self, obj):
        if obj.blood_group == 'UNK':
            return format_html('<span style="color:#888;">—</span>')
        return format_html(
            '<span style="background:#f8d7da;color:#842029;'
            'padding:2px 8px;border-radius:4px;font-weight:600;">{}</span>',
            obj.blood_group,
        )

    @admin.display(description='Status', ordering='is_active', boolean=False)
    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background:#d1e7dd;color:#0f5132;'
                'padding:2px 8px;border-radius:4px;">Active</span>'
            )
        return format_html(
            '<span style="background:#fff3cd;color:#664d03;'
            'padding:2px 8px;border-radius:4px;">Inactive</span>'
        )