"""Tests for the Diagnosis model + constraints."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
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


class DiagnosisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="dxd",
            email="dxd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="DX-1",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=100,
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="dxs",
            email="dxs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="P",
            last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543210",
            registered_by=cls.staff,
        )
        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(monday, time(10, 0))),
            reason="Test",
            booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)

        cls.gerd = ConditionCatalog.objects.create(code="K21.9", name="GERD")
        cls.hyper = ConditionCatalog.objects.create(code="I10", name="Hypertension")
        cls.cold = ConditionCatalog.objects.create(code="J00", name="Common cold")

    def test_create_diagnosis(self):
        d = Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        self.assertEqual(d.condition, self.gerd)
        self.assertFalse(d.is_primary)

    def test_str_representation(self):
        d = Diagnosis.objects.create(
            medical_record=self.mr,
            condition=self.gerd,
            is_primary=True,
        )
        s = str(d)
        self.assertIn("K21.9", s)
        self.assertIn("GERD", s)
        self.assertIn("PRIMARY", s)

    def test_duplicate_condition_rejected(self):
        Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        with self.assertRaises(IntegrityError):
            Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)

    def test_second_primary_rejected(self):
        Diagnosis.objects.create(
            medical_record=self.mr,
            condition=self.gerd,
            is_primary=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Diagnosis.objects.create(
                    medical_record=self.mr,
                    condition=self.hyper,
                    is_primary=True,
                )

    def test_multiple_non_primary_allowed(self):
        Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        Diagnosis.objects.create(medical_record=self.mr, condition=self.hyper)
        Diagnosis.objects.create(medical_record=self.mr, condition=self.cold)
        self.assertEqual(self.mr.diagnoses.count(), 3)

    def test_primary_appears_first_in_ordering(self):
        Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        Diagnosis.objects.create(medical_record=self.mr, condition=self.hyper)
        primary = Diagnosis.objects.create(
            medical_record=self.mr,
            condition=self.cold,
            is_primary=True,
        )
        first = self.mr.diagnoses.first()
        self.assertEqual(first, primary)

    def test_deleting_medical_record_cascades(self):
        Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        self.mr.delete()
        self.assertEqual(Diagnosis.objects.count(), 0)

    def test_condition_protected(self):
        """Cannot delete a condition that has diagnoses."""
        Diagnosis.objects.create(medical_record=self.mr, condition=self.gerd)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.gerd.delete()
