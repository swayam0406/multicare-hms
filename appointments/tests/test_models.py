"""Tests for the Appointment model — conflict detection is the critical part."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    """Return the date of the next occurrence of a weekday (0=Mon)."""
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class AppointmentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Cardio", code="CARD")
        cls.doctor_user = User.objects.create_user(
            username="drtest",
            email="dr@test.local",
            password="pass1234",
            first_name="Test",
            last_name="Doc",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doctor_user,
            department=cls.dept,
            license_number="LIC-1",
            specialty="X",
            qualifications="MBBS",
            consultation_fee=500,
            consultation_duration_minutes=20,
        )
        # Availability: Mondays 9-12, Wednesdays 14-17
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=2,
            start_time=time(14, 0),
            end_time=time(17, 0),
        )

        cls.staff = User.objects.create_user(
            username="rec",
            email="r@test.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="Pat",
            last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543210",
            registered_by=cls.staff,
        )

    def _make(self, start_dt, doctor=None, patient=None, status=Appointment.Status.SCHEDULED):
        return Appointment(
            patient=patient or self.patient,
            doctor=doctor or self.doctor,
            scheduled_start=start_dt,
            reason="Test",
            booked_by=self.staff,
            status=status,
        )

    def _monday_at(self, hh, mm=0):
        return timezone.make_aware(datetime.combine(_next_weekday(0), time(hh, mm)))

    def test_scheduled_end_auto_computed(self):
        appt = self._make(self._monday_at(10))
        appt.save()
        expected_end = appt.scheduled_start + timedelta(minutes=20)
        self.assertEqual(appt.scheduled_end, expected_end)

    def test_valid_appointment_passes_clean(self):
        appt = self._make(self._monday_at(10))
        appt.full_clean()  # should not raise

    def test_past_appointment_rejected(self):
        past = timezone.now() - timedelta(hours=1)
        appt = self._make(past)
        with self.assertRaises(ValidationError) as ctx:
            appt.full_clean()
        self.assertIn("scheduled_start", ctx.exception.message_dict)

    def test_outside_availability_rejected(self):
        # Monday 14:00 — not in Sharma's availability
        appt = self._make(self._monday_at(14))
        with self.assertRaises(ValidationError):
            appt.full_clean()

    def test_wrong_weekday_rejected(self):
        # Tuesday 10:00 — no availability configured
        tuesday = _next_weekday(1)
        appt = self._make(timezone.make_aware(datetime.combine(tuesday, time(10, 0))))
        with self.assertRaises(ValidationError):
            appt.full_clean()

    def test_overlap_with_active_appointment_rejected(self):
        first = self._make(self._monday_at(10))
        first.full_clean()
        first.save()
        # Overlaps: starts 5 min into the first appointment
        second = self._make(self._monday_at(10, 5))
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_back_to_back_appointments_allowed(self):
        first = self._make(self._monday_at(10))
        first.full_clean()
        first.save()
        # First runs 10:00-10:20; second starts 10:20 — no overlap
        second = self._make(self._monday_at(10, 20))
        second.full_clean()  # should not raise

    def test_cancelled_appointment_does_not_block_slot(self):
        first = self._make(self._monday_at(10), status=Appointment.Status.CANCELLED)
        first.save()  # skip clean — cancelled appointments may be historical
        # Same slot should now be available
        second = self._make(self._monday_at(10))
        second.full_clean()  # should not raise

    def test_editing_own_appointment_does_not_conflict_with_itself(self):
        appt = self._make(self._monday_at(10))
        appt.full_clean()
        appt.save()
        # Re-clean the existing appointment — should not conflict with itself
        appt.full_clean()

    def test_manager_upcoming_excludes_past(self):
        # Past appointment (bypass clean by saving directly)
        past_appt = self._make(timezone.now() - timedelta(days=1))
        past_appt.save()
        future = self._make(self._monday_at(10))
        future.save()
        upcoming = Appointment.objects.upcoming()
        self.assertIn(future, upcoming)
        self.assertNotIn(past_appt, upcoming)

    def test_manager_upcoming_excludes_cancelled(self):
        appt = self._make(self._monday_at(10), status=Appointment.Status.CANCELLED)
        appt.save()
        self.assertNotIn(appt, Appointment.objects.upcoming())

    def test_is_active_property(self):
        appt = self._make(self._monday_at(10))
        appt.save()
        self.assertTrue(appt.is_active)
        appt.status = Appointment.Status.COMPLETED
        self.assertFalse(appt.is_active)

    def test_is_terminal_property(self):
        appt = self._make(self._monday_at(10))
        appt.save()
        self.assertFalse(appt.is_terminal)
        appt.status = Appointment.Status.NO_SHOW
        self.assertTrue(appt.is_terminal)
