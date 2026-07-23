"""
Admin configuration for the accounts app.

Registers the custom User model with a UserAdmin that exposes
HMS-specific fields (role, phone, verification) alongside Django's
built-in user fields.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Custom admin for the HMS User model."""

    # ---------- List view ----------
    list_display = (
        'username',
        'email',
        'get_full_name',
        'role',
        'phone',
        'is_verified',
        'is_active',
        'is_staff',
        'date_joined',
    )
    list_display_links = ('username', 'email')
    list_filter = (
        'role',
        'is_verified',
        'is_active',
        'is_staff',
        'is_superuser',
        'date_joined',
    )
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    list_per_page = 25

    # ---------- Detail (change) view ----------
    fieldsets = (
        (None, {
            'fields': ('username', 'password'),
        }),
        (_('Personal Information'), {
            'fields': (
                'first_name',
                'last_name',
                'email',
                'phone',
                'date_of_birth',
                'address',
                'profile_picture',
            ),
        }),
        (_('Role & Verification'), {
            'fields': ('role', 'is_verified'),
        }),
        (_('Permissions'), {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        (_('Important Dates'), {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at'),
        }),
    )

    readonly_fields = ('last_login', 'date_joined', 'created_at', 'updated_at')

    # ---------- Add (create) view ----------
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'email',
                'first_name',
                'last_name',
                'role',
                'phone',
                'password1',
                'password2',
            ),
        }),
    )

    @admin.display(description='Full name', ordering='first_name')
    def get_full_name(self, obj):
        return obj.get_full_name() or '—'