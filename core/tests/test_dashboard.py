"""Tests for the admin dashboard view."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, Payment, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


class DashboardAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="d_admin", email="da@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )
        cls.doc = User.objects.create_user(
            username="d_doc", email="dd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.pat = User.objects.create_user(
            username="d_pat", email="dp@t.local",
            password="pass1234", role=User.Role.PATIENT,
        )

    def setUp(self):
        cache.clear()

    def test_admin_can_view(self):
        self.client.login(username="d_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_doctor_forbidden(self):
        self.client.login(username="d_doc", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_patient_forbidden(self):
        self.client.login(username="d_pat", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)


class DashboardStatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="ds_admin", email="dsa@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="ds_doc", email="dsd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="DS-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        for weekday in range(7):
            DoctorAvailability.objects.get_or_create(
                doctor=cls.doctor, weekday=weekday,
                defaults={"start_time": time(9, 0),
                          "end_time": time(17, 0)},
            )
        cls.staff = User.objects.create_user(
            username="ds_staff", email="dss@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="X", last_name="Y",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )

    def setUp(self):
        cache.clear()

    def test_appointments_today_counted(self):
        today = timezone.localdate()
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(10, 0))
            ),
            reason="Today", booked_by=self.staff,
        )
        self.client.login(username="ds_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["appointments"]["total"], 1)

    def test_outstanding_bills_counted(self):
        today = timezone.localdate()
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(11, 0))
            ),
            reason="B", booked_by=self.staff,
        )
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()

        self.client.login(username="ds_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["billing"]["outstanding"], 1)

    def test_revenue_today_sums_payments(self):
        today = timezone.localdate()
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(12, 0))
            ),
            reason="R", booked_by=self.staff,
        )
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        Payment.objects.create(
            bill=bill, amount=Decimal("200.00"),
            method="CASH", received_by=self.staff,
        )

        self.client.login(username="ds_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["billing"]["revenue_today"], Decimal("200.00"))

    def test_new_patient_today_counted(self):
        # self.patient was created today via setUpTestData
        self.client.login(username="ds_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        stats = response.context["stats"]
        self.assertGreaterEqual(stats["patients"]["new_today"], 1)

    def test_stats_are_cached(self):
        self.client.login(username="ds_admin", password="pass1234")
        response = self.client.get(reverse("core:dashboard"))
        first = response.context["stats"]["patients"]["total_active"]

        # Add a patient
        Patient.objects.create(
            first_name="New", last_name="Person",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543299",
            registered_by=self.staff,
        )

        # Same call — cached
        response2 = self.client.get(reverse("core:dashboard"))
        cached = response2.context["stats"]["patients"]["total_active"]
        self.assertEqual(first, cached)

        # Clear — see the new number
        cache.clear()
        response3 = self.client.get(reverse("core:dashboard"))
        fresh = response3.context["stats"]["patients"]["total_active"]
        self.assertEqual(fresh, first + 1)