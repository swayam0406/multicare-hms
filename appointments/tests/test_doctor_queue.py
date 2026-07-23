"""Tests for DoctorQueueView."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class DoctorQueueViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")

        # Doctor 1
        cls.doc_user = User.objects.create_user(
            username="drq",
            email="drq@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
            first_name="Queue",
            last_name="Test",
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="Q-1",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=100,
            consultation_duration_minutes=30,
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )

        # Orphan doctor (no profile) — for Http404 test
        cls.orphan_doc = User.objects.create_user(
            username="orphan_doc",
            email="orphan@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )

        # Admin (should be forbidden)
        cls.admin = User.objects.create_user(
            username="qadmin",
            email="a@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )

        # Staff for booking
        cls.staff = User.objects.create_user(
            username="qstaff",
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

        # Book appointment for next Monday 10:00
        cls.next_monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(cls.next_monday, time(10, 0))),
            reason="Test visit",
            booked_by=cls.staff,
        )

    # ---------- Access control ----------

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("appointments:queue"))
        self.assertEqual(response.status_code, 302)

    def test_admin_forbidden(self):
        self.client.login(username="qadmin", password="pass1234")
        response = self.client.get(reverse("appointments:queue"))
        self.assertEqual(response.status_code, 403)

    def test_doctor_without_profile_gets_404(self):
        self.client.login(username="orphan_doc", password="pass1234")
        response = self.client.get(reverse("appointments:queue"))
        self.assertEqual(response.status_code, 404)

    def test_doctor_can_access_queue(self):
        self.client.login(username="drq", password="pass1234")
        response = self.client.get(reverse("appointments:queue"))
        self.assertEqual(response.status_code, 200)

    # ---------- Date filter ----------

    def test_defaults_to_today(self):
        self.client.login(username="drq", password="pass1234")
        response = self.client.get(reverse("appointments:queue"))
        self.assertTrue(response.context["is_today"])
        self.assertEqual(response.context["selected_date"], timezone.localdate())

    def test_shows_appointment_on_correct_date(self):
        self.client.login(username="drq", password="pass1234")
        response = self.client.get(
            reverse("appointments:queue"),
            {"date": self.next_monday.isoformat()},
        )
        self.assertEqual(response.context["total"], 1)
        self.assertContains(response, "Test visit")

    def test_hides_appointment_on_other_date(self):
        self.client.login(username="drq", password="pass1234")
        other = self.next_monday + timedelta(days=1)
        response = self.client.get(
            reverse("appointments:queue"),
            {"date": other.isoformat()},
        )
        self.assertEqual(response.context["total"], 0)

    def test_invalid_date_silently_falls_back_to_today(self):
        self.client.login(username="drq", password="pass1234")
        response = self.client.get(
            reverse("appointments:queue"),
            {"date": "junk"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_date"], timezone.localdate())

    def test_appointment_from_another_doctor_hidden(self):
        # Book for our patient with a totally different doctor
        other_user = User.objects.create_user(
            username="drq2",
            email="drq2@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        other_doc = Doctor.objects.create(
            user=other_user,
            department=self.dept,
            license_number="Q-2",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=100,
        )
        DoctorAvailability.objects.create(
            doctor=other_doc,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        Appointment.objects.create(
            patient=self.patient,
            doctor=other_doc,
            scheduled_start=timezone.make_aware(datetime.combine(self.next_monday, time(11, 0))),
            reason="Other doctor's appt",
            booked_by=self.staff,
        )

        self.client.login(username="drq", password="pass1234")
        response = self.client.get(
            reverse("appointments:queue"),
            {"date": self.next_monday.isoformat()},
        )
        # Should only see our own doctor's appointment
        self.assertEqual(response.context["total"], 1)
        self.assertNotContains(response, "Other doctor's appt")
