"""URL configuration for the medical_records app."""

from django.urls import path

from .views import ConsultationView

app_name = "medical_records"

urlpatterns = [
    path(
        "consultation/<int:appointment_pk>/",
        ConsultationView.as_view(),
        name="consultation",
    ),
]