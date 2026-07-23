"""Tests for appointments.services.available_slots."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from appointments.services import available_slots
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class AvailableSlotsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="d",
            email="d@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
            first_name="D",
            last_name="One",
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="L",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=100,
            consultation_duration_minutes=30,
        )
        # Mon 09:00-12:00 (six 30-min slots)
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="s",
            email="s@t.local",
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

    def test_slots_generated_for_available_day(self):
        monday = _next_weekday(0)
        slots = available_slots(self.doctor, monday)
        # 9:00, 9:30, 10:00, 10:30, 11:00, 11:30 → 6 slots
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[0]["value"], "09:00")
        self.assertEqual(slots[-1]["value"], "11:30")

    def test_no_slots_when_no_availability(self):
        tuesday = _next_weekday(1)
        slots = available_slots(self.doctor, tuesday)
        self.assertEqual(slots, [])

    def test_booked_slot_removed(self):
        monday = _next_weekday(0)
        booked_start = timezone.make_aware(datetime.combine(monday, time(10, 0)))
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=booked_start,
            reason="Test",
            booked_by=self.staff,
        )
        slots = available_slots(self.doctor, monday)
        values = [s["value"] for s in slots]
        self.assertNotIn("10:00", values)
        self.assertEqual(len(slots), 5)

    def test_cancelled_appointment_does_not_block_slot(self):
        monday = _next_weekday(0)
        booked_start = timezone.make_aware(datetime.combine(monday, time(10, 0)))
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=booked_start,
            reason="Test",
            booked_by=self.staff,
            status=Appointment.Status.CANCELLED,
        )
        slots = available_slots(self.doctor, monday)
        values = [s["value"] for s in slots]
        self.assertIn("10:00", values)


class AvailableSlotsAPITests(TestCase):
    """Test the JSON endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="d2",
            email="d2@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="L2",
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
            username="s2",
            email="s2@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )

    def test_anonymous_forbidden(self):
        response = self.client.get("/appointments/api/slots/")
        self.assertEqual(response.status_code, 302)

    def test_missing_params_returns_400(self):
        self.client.login(username="s2", password="pass1234")
        response = self.client.get("/appointments/api/slots/")
        self.assertEqual(response.status_code, 400)

    def test_valid_request_returns_slots(self):
        self.client.login(username="s2", password="pass1234")
        monday = _next_weekday(0).isoformat()
        response = self.client.get(
            f"/appointments/api/slots/?doctor={self.doctor.pk}&date={monday}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("slots", data)
        self.assertGreater(len(data["slots"]), 0)

    def test_past_date_rejected(self):
        self.client.login(username="s2", password="pass1234")
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.client.get(f"/appointments/api/slots/?doctor={self.doctor.pk}&date={past}")
        self.assertEqual(response.status_code, 400)
