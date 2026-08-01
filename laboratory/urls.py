"""URL configuration for the laboratory app."""

from django.urls import path

from .views import (
    LabOrderCreateView,
    LabOrderDetailView,
    LabOrderTransitionView,
    LabQueueView,
    LabReportPdfView,
    LabResultEntryView,
)

app_name = "laboratory"

urlpatterns = [
    # T-7.3
    path("orders/create/<int:appointment_pk>/", LabOrderCreateView.as_view(), name="order_create"),
    # T-7.4
    path("queue/", LabQueueView.as_view(), name="queue"),
    path("orders/<int:pk>/", LabOrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/transition/", LabOrderTransitionView.as_view(), name="order_transition"),
    path("orders/<int:pk>/results/", LabResultEntryView.as_view(), name="result_entry"),
    path("orders/<int:pk>/pdf/", LabReportPdfView.as_view(), name="lab_report_pdf"),
]
