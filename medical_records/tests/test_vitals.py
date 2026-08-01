"""Tests for the Vitals model."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from medical_records.models import MedicalRecord, Vitals
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class VitalsSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="v_doc", email="vd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="V-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="v_staff", email="vs@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="A", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient, doctor=cls.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(monday, time(10, 0))
            ),
            reason="T", booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)


class VitalsCreationTests(VitalsSetup):
    def test_create_minimal_vitals(self):
        v = Vitals.objects.create(medical_record=self.mr)
        self.assertIsNotNone(v.pk)
        self.assertEqual(v.medical_record, self.mr)

    def test_create_full_vitals(self):
        v = Vitals.objects.create(
            medical_record=self.mr,
            bp_systolic=120,
            bp_diastolic=80,
            pulse=72,
            respiratory_rate=16,
            spo2=98,
            temperature=Decimal("36.8"),
            weight_kg=Decimal("70.5"),
            height_cm=Decimal("175.0"),
            recorded_by=self.doc_user,
        )
        self.assertEqual(v.bp_systolic, 120)
        self.assertEqual(v.bp_diastolic, 80)
        self.assertEqual(v.temperature, Decimal("36.8"))

    def test_one_vitals_per_medical_record(self):
        Vitals.objects.create(medical_record=self.mr)
        with self.assertRaises(IntegrityError):
            Vitals.objects.create(medical_record=self.mr)

    def test_recorded_at_auto_set(self):
        v = Vitals.objects.create(medical_record=self.mr)
        self.assertIsNotNone(v.recorded_at)


class VitalsPropertiesTests(VitalsSetup):
    """If the model exposes BMI as a property, these tests exercise it."""

    def test_bmi_computed_when_height_and_weight_present(self):
        v = Vitals.objects.create(
            medical_record=self.mr,
            weight_kg=Decimal("70.0"),
            height_cm=Decimal("175.0"),
        )
        bmi_attr = getattr(v, "bmi", None)
        if bmi_attr is None:
            self.skipTest("Vitals has no bmi property in this build.")
        # 70 / (1.75^2) = ~22.86
        self.assertAlmostEqual(float(bmi_attr), 22.86, places=1)

    def test_bmi_none_without_height_or_weight(self):
        v = Vitals.objects.create(medical_record=self.mr)
        bmi_attr = getattr(v, "bmi", "NOT_PRESENT")
        if bmi_attr == "NOT_PRESENT":
            self.skipTest("Vitals has no bmi property in this build.")
        self.assertIsNone(bmi_attr)


class VitalsCascadeTests(VitalsSetup):
    def test_medical_record_delete_cascades(self):
        Vitals.objects.create(medical_record=self.mr)
        self.mr.delete()
        self.assertEqual(Vitals.objects.count(), 0)