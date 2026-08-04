"""Tests for BillListView."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class BillListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="bld",
            email="bld@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="BLD-1",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="bls",
            email="bls@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="Alice",
            last_name="Anderson",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.FEMALE,
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
        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="Consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )

    def _url(self, **params):
        base = reverse("billing:list")
        if not params:
            return base
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{q}"

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_staff_can_access(self):
        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_patient_forbidden(self):
        User.objects.create_user(
            username="blp",
            email="blp@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        self.client.login(username="blp", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_empty_state(self):
        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["summary"]["count"], 0)
        self.assertContains(response, "No bills found")

    def test_bill_appears_in_list(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)

        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["summary"]["count"], 1)
        self.assertContains(response, bill.bill_number)
        self.assertContains(response, "Alice")

    def test_patient_search_by_name(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)

        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url(patient="Anderson"))
        self.assertEqual(response.context["summary"]["count"], 1)

        response = self.client.get(self._url(patient="NoSuchName"))
        self.assertEqual(response.context["summary"]["count"], 0)

    def test_search_by_bill_number(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)

        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url(patient=bill.bill_number))
        self.assertEqual(response.context["summary"]["count"], 1)

    def test_status_filter(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()

        self.client.login(username="bls", password="pass1234")
        # DRAFT filter — nothing
        response = self.client.get(self._url(status="DRAFT"))
        self.assertEqual(response.context["summary"]["count"], 0)

        # FINALIZED filter — one
        response = self.client.get(self._url(status="FINALIZED"))
        self.assertEqual(response.context["summary"]["count"], 1)

    def test_outstanding_quick_preset(self):
        # Draft bill — not in outstanding
        draft = Bill.objects.create(appointment=self.appt, patient=self.patient)

        # Finalized bill — should show up
        DoctorAvailability.objects.create(
            doctor=self.doctor,
            weekday=1,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        tuesday = _next_weekday(1)
        appt2 = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(tuesday, time(10, 0))),
            reason="Test",
            booked_by=self.staff,
        )
        bill2 = Bill.objects.create(appointment=appt2, patient=self.patient)
        BillItem.objects.create(bill=bill2, service=self.cons, quantity=1)
        bill2.refresh_from_db()
        bill2.finalize()

        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url(quick="outstanding"))
        self.assertEqual(response.context["summary"]["count"], 1)
        self.assertContains(response, bill2.bill_number)
        self.assertNotContains(response, draft.bill_number)

    def test_summary_totals(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()

        self.client.login(username="bls", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(
            response.context["summary"]["total_billed"],
            Decimal("500.00"),
        )
