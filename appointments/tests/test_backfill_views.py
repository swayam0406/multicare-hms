"""Backfill view tests from Sprint 4:
  - AppointmentListView (staff filters)
  - MyAppointmentsView (patient self-service)
  - AppointmentTransitionView (state machine)
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

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


class SharedSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")

        cls.doc_user = User.objects.create_user(
            username="av_doc", email="avd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="AV-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )

        cls.doc2_user = User.objects.create_user(
            username="av_doc2", email="avd2@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor2 = Doctor.objects.create(
            user=cls.doc2_user, department=cls.dept,
            license_number="AV-2", specialty="y",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )

        # Availability for all weekdays to make appt creation easy
        for weekday in range(7):
            for doc in [cls.doctor, cls.doctor2]:
                DoctorAvailability.objects.get_or_create(
                    doctor=doc, weekday=weekday,
                    defaults={"start_time": time(9, 0),
                              "end_time": time(17, 0)},
                )

        cls.staff = User.objects.create_user(
            username="av_staff", email="avs@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="av_admin", email="ava@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )

        cls.pat_user = User.objects.create_user(
            username="av_pat", email="avp@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )
        cls.patient = Patient.objects.create(
            first_name="Alice", last_name="Anderson",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.FEMALE, phone="9876543210",
            registered_by=cls.staff, user=cls.pat_user,
        )

        cls.other_pat_user = User.objects.create_user(
            username="av_pat2", email="avp2@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )
        cls.other_patient = Patient.objects.create(
            first_name="Bob", last_name="Brown",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543211",
            registered_by=cls.staff, user=cls.other_pat_user,
        )

    def _make_appt(self, doctor=None, patient=None, days_offset=1,
                   hour=10, status="SCHEDULED"):
        """Helper: create appt N days from today at HH:00."""
        doctor = doctor or self.doctor
        patient = patient or self.patient
        day = timezone.localdate() + timedelta(days=days_offset)
        return Appointment.objects.create(
            patient=patient, doctor=doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(day, time(hour, 0))
            ),
            reason="Test", booked_by=self.staff, status=status,
        )


# ============================================================
# AppointmentListView
# ============================================================


class AppointmentListAccessTests(SharedSetup):
    def _url(self):
        return reverse("appointments:list")

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_staff_can_access(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access(self):
        self.client.login(username="av_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_patient_forbidden(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)


class AppointmentListFilterTests(SharedSetup):
    def _url(self):
        return reverse("appointments:list")

    def setUp(self):
        # A future appt (SCHEDULED) with doctor 1
        self.future_appt = self._make_appt(
            doctor=self.doctor, days_offset=5, hour=10,
            status="SCHEDULED",
        )
        # A completed past appt with doctor 2
        self.past_appt = self._make_appt(
            doctor=self.doctor2, days_offset=-5, hour=14,
            status="COMPLETED",
        )

    def test_no_filter_returns_all(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        appts = list(response.context["appointments"])
        self.assertIn(self.future_appt, appts)
        self.assertIn(self.past_appt, appts)

    def test_filter_by_doctor(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url() + f"?doctor={self.doctor.pk}")
        appts = list(response.context["appointments"])
        self.assertIn(self.future_appt, appts)
        self.assertNotIn(self.past_appt, appts)

    def test_filter_by_status(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url() + "?status=COMPLETED")
        appts = list(response.context["appointments"])
        self.assertIn(self.past_appt, appts)
        self.assertNotIn(self.future_appt, appts)

    def test_quick_today(self):
        today_appt = self._make_appt(
            doctor=self.doctor, days_offset=0, hour=11,
            status="SCHEDULED",
        )
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url() + "?quick=today")
        appts = list(response.context["appointments"])
        self.assertIn(today_appt, appts)
        self.assertNotIn(self.future_appt, appts)

    def test_quick_week(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url() + "?quick=week")
        appts = list(response.context["appointments"])
        # Future appt (5 days ahead) is within the week window
        self.assertIn(self.future_appt, appts)
        # Past appt (-5 days) is NOT
        self.assertNotIn(self.past_appt, appts)

    def test_invalid_doctor_filter_ignored(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url() + "?doctor=abc")
        self.assertEqual(response.status_code, 200)
        # Falls back to no filter
        appts = list(response.context["appointments"])
        self.assertIn(self.future_appt, appts)
        self.assertIn(self.past_appt, appts)

    def test_context_contains_doctors_and_statuses(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url())
        self.assertIn("doctors", response.context)
        self.assertIn("statuses", response.context)
        self.assertIn("filters", response.context)


# ============================================================
# MyAppointmentsView
# ============================================================


class MyAppointmentsAccessTests(SharedSetup):
    def _url(self):
        return reverse("appointments:my_appointments")

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_staff_forbidden(self):
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_patient_can_access(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)


class MyAppointmentsContentTests(SharedSetup):
    def _url(self):
        return reverse("appointments:my_appointments")

    def setUp(self):
        self.upcoming = self._make_appt(
            doctor=self.doctor, patient=self.patient,
            days_offset=5, hour=10, status="SCHEDULED",
        )
        self.past = self._make_appt(
            doctor=self.doctor, patient=self.patient,
            days_offset=-5, hour=14, status="COMPLETED",
        )
        self.cancelled = self._make_appt(
            doctor=self.doctor, patient=self.patient,
            days_offset=7, hour=11, status="CANCELLED",
        )
        # Another patient's appt — should NOT appear
        self.other_appt = self._make_appt(
            doctor=self.doctor, patient=self.other_patient,
            days_offset=3, hour=15, status="SCHEDULED",
        )

    def test_upcoming_includes_scheduled(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        upcoming = list(response.context["upcoming"])
        self.assertIn(self.upcoming, upcoming)

    def test_upcoming_excludes_cancelled(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        upcoming = list(response.context["upcoming"])
        self.assertNotIn(self.cancelled, upcoming)

    def test_past_includes_completed(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        past = list(response.context["past"])
        self.assertIn(self.past, past)

    def test_only_patients_own_appointments_shown(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        upcoming = list(response.context["upcoming"])
        past = list(response.context["past"])
        self.assertNotIn(self.other_appt, upcoming)
        self.assertNotIn(self.other_appt, past)

    def test_counts_provided(self):
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["upcoming_count"], 1)
        self.assertEqual(response.context["past_count"], 1)


# ============================================================
# AppointmentTransitionView
# ============================================================


class TransitionAccessTests(SharedSetup):
    def _url(self, appt):
        return reverse("appointments:transition", kwargs={"pk": appt.pk})

    def test_staff_can_confirm_scheduled(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "CONFIRMED",
        })
        self.assertEqual(response.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "CONFIRMED")

    def test_patient_forbidden(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_pat", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "CONFIRMED",
        })
        self.assertEqual(response.status_code, 403)


class TransitionValidationTests(SharedSetup):
    def _url(self, appt):
        return reverse("appointments:transition", kwargs={"pk": appt.pk})

    def test_invalid_transition_rejected(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "COMPLETED",  # SCHEDULED -> COMPLETED not valid
        })
        appt.refresh_from_db()
        self.assertEqual(appt.status, "SCHEDULED")

    def test_cancel_requires_reason(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "CANCELLED",
        })
        appt.refresh_from_db()
        self.assertNotEqual(appt.status, "CANCELLED")

    def test_cancel_with_reason(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        self.client.post(self._url(appt), {
            "new_status": "CANCELLED",
            "cancelled_reason": "Patient rescheduled by phone.",
        })
        appt.refresh_from_db()
        self.assertEqual(appt.status, "CANCELLED")
        self.assertEqual(
            appt.cancelled_reason,
            "Patient rescheduled by phone.",
        )


class ClinicalActionAuthTests(SharedSetup):
    """
    IN_PROGRESS / COMPLETED / NO_SHOW require the owning doctor or admin —
    not just any staff member.
    """

    def _url(self, appt):
        return reverse("appointments:transition", kwargs={"pk": appt.pk})

    def test_owning_doctor_can_start_consultation(self):
        appt = self._make_appt(doctor=self.doctor, status="CONFIRMED")
        self.client.login(username="av_doc", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "IN_PROGRESS",
        })
        self.assertEqual(response.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "IN_PROGRESS")

    def test_other_doctor_forbidden_from_clinical_action(self):
        appt = self._make_appt(doctor=self.doctor, status="CONFIRMED")
        self.client.login(username="av_doc2", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "IN_PROGRESS",
        })
        self.assertEqual(response.status_code, 403)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "CONFIRMED")

    def test_admin_can_start_any_consultation(self):
        appt = self._make_appt(doctor=self.doctor, status="CONFIRMED")
        self.client.login(username="av_admin", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "IN_PROGRESS",
        })
        self.assertEqual(response.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "IN_PROGRESS")

    def test_receptionist_cannot_complete(self):
        appt = self._make_appt(doctor=self.doctor, status="IN_PROGRESS")
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.post(self._url(appt), {
            "new_status": "COMPLETED",
        })
        self.assertEqual(response.status_code, 403)


class TransitionNoteTrailTests(SharedSetup):
    def _url(self, appt):
        return reverse("appointments:transition", kwargs={"pk": appt.pk})

    def test_note_appended_to_appointment_notes(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        self.client.post(self._url(appt), {
            "new_status": "CONFIRMED",
            "notes": "Confirmed via phone.",
        })
        appt.refresh_from_db()
        self.assertIn("Confirmed via phone.", appt.notes)

    def test_get_method_not_allowed(self):
        appt = self._make_appt(status="SCHEDULED")
        self.client.login(username="av_staff", password="pass1234")
        response = self.client.get(self._url(appt))
        self.assertEqual(response.status_code, 405)