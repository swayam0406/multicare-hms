"""Tests for PrescriptionPdfView."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from medical_records.models import (
    MedicalRecord,
    MedicationCatalog,
    Prescription,
    PrescriptionItem,
)
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class PrescriptionPdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")

        cls.doc_user = User.objects.create_user(
            username="rx_doc", email="rd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="RX-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )

        cls.other_doc_user = User.objects.create_user(
            username="rx_other_doc", email="rod@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.other_doctor = Doctor.objects.create(
            user=cls.other_doc_user, department=cls.dept,
            license_number="RX-2", specialty="y",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )

        cls.staff = User.objects.create_user(
            username="rx_staff", email="rs@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="rx_admin", email="ra@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )

        cls.patient_user = User.objects.create_user(
            username="rx_pat", email="rp@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )
        cls.patient = Patient.objects.create(
            first_name="A", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff, user=cls.patient_user,
        )

        cls.other_pat_user = User.objects.create_user(
            username="rx_pat2", email="rp2@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )
        cls.other_patient = Patient.objects.create(
            first_name="B", last_name="Two",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543211",
            registered_by=cls.staff, user=cls.other_pat_user,
        )

        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient, doctor=cls.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(monday, time(10, 0))
            ),
            reason="Test", booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)
        cls.rx = Prescription.objects.create(medical_record=cls.mr)
        med = MedicationCatalog.objects.create(
            name="Paracetamol", strength="500mg", form="TABLET",
        )
        PrescriptionItem.objects.create(
            prescription=cls.rx, medication=med,
            dose="1 tablet", frequency="TID", duration_days=5,
        )

    def _url(self):
        return reverse("medical_records:prescription_pdf",
                       kwargs={"pk": self.rx.pk})

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_owning_doctor_downloads(self):
        self.client.login(username="rx_doc", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_admin_downloads(self):
        self.client.login(username="rx_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_owning_patient_downloads(self):
        self.client.login(username="rx_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_other_doctor_forbidden(self):
        self.client.login(username="rx_other_doc", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_other_patient_forbidden(self):
        self.client.login(username="rx_pat2", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_filename_uses_visit_date_and_patient_id(self):
        self.client.login(username="rx_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertIn(
            "prescription-",
            response["Content-Disposition"],
        )
        self.assertIn(
            f"{self.patient.patient_id}.pdf",
            response["Content-Disposition"],
        )
