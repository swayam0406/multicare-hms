"""URL configuration for the doctors app."""

from django.urls import path

from .views import DoctorDetailView, DoctorListView

app_name = "doctors"

urlpatterns = [
    path("", DoctorListView.as_view(), name="list"),
    path("<int:pk>/", DoctorDetailView.as_view(), name="detail"),
]
