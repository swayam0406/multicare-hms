"""Tests for the doctors app models."""

from datetime import time

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from doctors.models import Department, Doctor, DoctorAvailability

User = get_user_model()


class DepartmentModelTests(TestCase):
    def test_code_is_uppercased_on_save(self):
        dept = Department.objects.create(name="Neurology", code="neuro")
        self.assertEqual(dept.code, "NEURO")

    def test_code_is_stripped_on_save(self):
        dept = Department.objects.create(name="Dermatology", code="  derm  ")
        self.assertEqual(dept.code, "DERM")

    def test_name_uniqueness(self):
        Department.objects.create(name="Cardiology", code="CARD")
        with self.assertRaises(IntegrityError):
            Department.objects.create(name="Cardiology", code="CARD2")

    def test_default_is_active_true(self):
        dept = Department.objects.create(name="Oncology", code="ONC")
        self.assertTrue(dept.is_active)

    def test_str_representation(self):
        dept = Department.objects.create(name="ENT", code="ENT")
        self.assertEqual(str(dept), "ENT (ENT)")


class DoctorModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Cardiology", code="CARD")
        cls.user = User.objects.create_user(
            username="drtest",
            email="drtest@test.local",
            password="pass1234",
            first_name="Test",
            last_name="Doctor",
            role=User.Role.DOCTOR,
        )

    def _create_doctor(self, **overrides):
        defaults = {
            "user": self.user,
            "department": self.dept,
            "license_number": "TEST-001",
            "specialty": "General",
            "qualifications": "MBBS",
            "consultation_fee": 500,
        }
        defaults.update(overrides)
        return Doctor.objects.create(**defaults)

    def test_str_includes_dr_prefix_and_department_code(self):
        doc = self._create_doctor()
        self.assertEqual(str(doc), "Dr. Test Doctor (CARD)")

    def test_full_name_uses_get_full_name(self):
        doc = self._create_doctor()
        self.assertEqual(doc.full_name, "Test Doctor")

    def test_display_name_includes_dr_prefix(self):
        doc = self._create_doctor()
        self.assertEqual(doc.display_name, "Dr. Test Doctor")

    def test_license_number_unique(self):
        self._create_doctor(license_number="LIC-1")
        other_user = User.objects.create_user(
            username="drtest2",
            email="drtest2@test.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        with self.assertRaises(IntegrityError):
            Doctor.objects.create(
                user=other_user,
                department=self.dept,
                license_number="LIC-1",  # duplicate
                specialty="X",
                qualifications="MBBS",
                consultation_fee=100,
            )

    def test_default_slot_duration(self):
        doc = self._create_doctor()
        self.assertEqual(doc.consultation_duration_minutes, 15)

    def test_manager_available_excludes_unavailable(self):
        doc = self._create_doctor()
        self.assertIn(doc, Doctor.objects.available())
        doc.is_available_for_booking = False
        doc.save()
        self.assertNotIn(doc, Doctor.objects.available())


class DoctorAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Cardiology", code="CARD")
        cls.user = User.objects.create_user(
            username="dravail",
            email="dravail@test.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doc = Doctor.objects.create(
            user=cls.user,
            department=cls.dept,
            license_number="AV-001",
            specialty="X",
            qualifications="MBBS",
            consultation_fee=100,
        )

    def test_create_availability(self):
        av = DoctorAvailability.objects.create(
            doctor=self.doc,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        self.assertEqual(av.weekday, 0)

    def test_end_before_start_rejected(self):
        with self.assertRaises(IntegrityError):
            DoctorAvailability.objects.create(
                doctor=self.doc,
                weekday=0,
                start_time=time(12, 0),
                end_time=time(9, 0),
            )

    def test_duplicate_start_time_rejected(self):
        DoctorAvailability.objects.create(
            doctor=self.doc,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        with self.assertRaises(IntegrityError):
            DoctorAvailability.objects.create(
                doctor=self.doc,
                weekday=0,
                start_time=time(9, 0),
                end_time=time(11, 0),
            )

    def test_str_representation(self):
        av = DoctorAvailability.objects.create(
            doctor=self.doc,
            weekday=2,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        self.assertIn("Wednesday", str(av))
        self.assertIn("09:00", str(av))
