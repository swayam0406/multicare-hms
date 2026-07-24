"""Tests for PatientClinicalHistoryView."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from medical_records.models import ConditionCatalog, Diagnosis, MedicalRecord
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class PatientHistoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="ph", email="ph@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="PH-1", specialty="x",
            qualifications="MBBS", consultation_fee=100,
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="phs", email="phs@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="P", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        cls.other_patient = Patient.objects.create(
            first_name="Q", last_name="Two",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.FEMALE, phone="9876543211",
            registered_by=cls.staff,
        )

        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient, doctor=cls.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(monday, time(10, 0))
            ),
            reason="Test", booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(
            appointment=cls.appt,
            chief_complaint="Persistent cough",
        )
        cls.cold = ConditionCatalog.objects.create(code="J00", name="Common cold")
        Diagnosis.objects.create(
            medical_record=cls.mr, condition=cls.cold, is_primary=True,
        )

    def _url(self, patient=None):
        p = patient or self.patient
        return reverse(
            "patients:history", kwargs={"patient_id": p.patient_id}
        )

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_staff_can_access(self):
        self.client.login(username="phs", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Persistent cough")
        self.assertContains(response, "J00")

    def test_patient_forbidden(self):
        pat = User.objects.create_user(
            username="phpat", email="phpat@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )
        self.client.login(username="phpat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_only_patients_own_records_shown(self):
        """Other patient's history page doesn't show this patient's records."""
        self.client.login(username="phs", password="pass1234")
        response = self.client.get(self._url(self.other_patient))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Persistent cough")
        self.assertNotContains(response, "J00")

    def test_visit_count_in_context(self):
        self.client.login(username="phs", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["visit_count"], 1)

    def test_appointments_without_medical_record_hidden(self):
        """An appointment with no medical record isn't shown."""
        tuesday = _next_weekday(1)
        DoctorAvailability.objects.create(
            doctor=self.doctor, weekday=1,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(tuesday, time(10, 0))
            ),
            reason="No record yet", booked_by=self.staff,
        )
        self.client.login(username="phs", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["visit_count"], 1)
        self.assertNotContains(response, "No record yet")