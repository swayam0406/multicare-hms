"""URL configuration for multicare_hms project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("patients/", include("patients.urls", namespace="patients")),
    path("doctors/", include("doctors.urls", namespace="doctors")),
    path("appointments/", include("appointments.urls", namespace="appointments")),
    path("medical-records/", include("medical_records.urls", namespace="medical_records")),
    path("", include("core.urls", namespace="core")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)