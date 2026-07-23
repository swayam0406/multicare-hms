"""Tests for the Patient model."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from patients.models import Patient

User = get_user_model()


class PatientModelTests(TestCase):
    """Test business logic of the Patient model."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff1",
            email="staff1@test.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )

    def _create_patient(self, **overrides):
        defaults = {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": date(1990, 1, 15),
            "gender": Patient.Gender.MALE,
            "phone": "9876543210",
            "registered_by": self.staff,
        }
        defaults.update(overrides)
        return Patient.objects.create(**defaults)

    def test_patient_id_auto_generated(self):
        p = self._create_patient()
        year = date.today().year
        self.assertTrue(p.patient_id.startswith(f"MC-{year}-"))
        self.assertEqual(len(p.patient_id), 13)  # MC-YYYY-NNNNN

    def test_patient_id_sequential(self):
        p1 = self._create_patient()
        p2 = self._create_patient(first_name="Jane")
        p3 = self._create_patient(first_name="Jack")

        year = date.today().year
        self.assertEqual(p1.patient_id, f"MC-{year}-00001")
        self.assertEqual(p2.patient_id, f"MC-{year}-00002")
        self.assertEqual(p3.patient_id, f"MC-{year}-00003")

    def test_patient_id_not_regenerated_on_save(self):
        p = self._create_patient()
        original = p.patient_id
        p.first_name = "Changed"
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.patient_id, original)

    def test_full_name_property(self):
        p = self._create_patient(first_name="John", last_name="Doe")
        self.assertEqual(p.full_name, "John Doe")

    def test_age_property(self):
        today = date.today()
        # Born 25 years ago exactly
        p = self._create_patient(
            date_of_birth=date(today.year - 25, today.month, today.day),
        )
        self.assertEqual(p.age, 25)

    def test_age_before_birthday_this_year(self):
        today = date.today()
        # Birthday is tomorrow — still 24
        tomorrow = today + timedelta(days=1)
        if tomorrow.year != today.year:
            self.skipTest("Edge case around year boundary")
        p = self._create_patient(
            date_of_birth=date(today.year - 25, tomorrow.month, tomorrow.day),
        )
        self.assertEqual(p.age, 24)

    def test_default_is_active_true(self):
        p = self._create_patient()
        self.assertTrue(p.is_active)

    def test_default_blood_group_unknown(self):
        p = self._create_patient()
        self.assertEqual(p.blood_group, Patient.BloodGroup.UNKNOWN)

    def test_str_representation(self):
        p = self._create_patient(first_name="John", last_name="Doe")
        self.assertIn("John Doe", str(p))
        self.assertIn(p.patient_id, str(p))


class PatientManagerTests(TestCase):
    """Test the custom PatientManager."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff2",
            email="s2@test.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )

    def _create(self, is_active=True, first_name="X"):
        return Patient.objects.create(
            first_name=first_name,
            last_name="Test",
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.MALE,
            phone="9876543210",
            is_active=is_active,
            registered_by=self.staff,
        )

    def test_active_returns_only_active(self):
        self._create(is_active=True, first_name="A")
        self._create(is_active=True, first_name="B")
        self._create(is_active=False, first_name="C")
        self.assertEqual(Patient.objects.active().count(), 2)

    def test_inactive_returns_only_inactive(self):
        self._create(is_active=True, first_name="A")
        self._create(is_active=False, first_name="B")
        self.assertEqual(Patient.objects.inactive().count(), 1)

    def test_default_manager_returns_all(self):
        self._create(is_active=True, first_name="A")
        self._create(is_active=False, first_name="B")
        self.assertEqual(Patient.objects.count(), 2)
