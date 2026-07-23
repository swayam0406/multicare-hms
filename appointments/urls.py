"""URL configuration for the appointments app."""

from django.urls import path

from .views import (
    AppointmentCreateView,
    AppointmentDetailView,
    AppointmentListView,
    AppointmentTransitionView,
    AvailableSlotsView,
    DoctorQueueView,
    MyAppointmentsView,
)

app_name = "appointments"

urlpatterns = [
    path("", AppointmentListView.as_view(), name="list"),
    path("book/", AppointmentCreateView.as_view(), name="book"),
    path("queue/", DoctorQueueView.as_view(), name="queue"),
    path("my/", MyAppointmentsView.as_view(), name="my_appointments"),
    path("api/slots/", AvailableSlotsView.as_view(), name="api_slots"),
    path("<int:pk>/", AppointmentDetailView.as_view(), name="detail"),
    path("<int:pk>/transition/", AppointmentTransitionView.as_view(), name="transition"),
]
