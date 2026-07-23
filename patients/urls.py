"""URL configuration for the patients app."""

from django.urls import path

from .views import (
    MyPatientRecordView,
    PatientCreateView,
    PatientDetailView,
    PatientListView,
    PatientToggleActiveView,
    PatientUpdateView,
)

app_name = 'patients'

urlpatterns = [
    path('', PatientListView.as_view(), name='list'),
    path('register/', PatientCreateView.as_view(), name='register'),
    path('my-record/', MyPatientRecordView.as_view(), name='my_record'),
    path('<str:patient_id>/', PatientDetailView.as_view(), name='detail'),
    path('<str:patient_id>/edit/', PatientUpdateView.as_view(), name='edit'),
    path('<str:patient_id>/toggle-active/', PatientToggleActiveView.as_view(),
         name='toggle_active'),
]