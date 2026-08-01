"""URL configuration for the medical_records app."""

from django.urls import path

from .views import ConsultationView, PrescriptionPdfView

app_name = "medical_records"

urlpatterns = [
    path(
        "consultation/<int:appointment_pk>/",
        ConsultationView.as_view(),
        name="consultation",
    ),
    path("prescriptions/<int:pk>/pdf/", PrescriptionPdfView.as_view(), name="prescription_pdf"),
]
