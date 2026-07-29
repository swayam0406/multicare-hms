"""Tests for the outstanding_bills_count template tag."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, Payment, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class OutstandingBillsCountTagTests(TestCase):
    """Assert the tag returns the correct count of unpaid bills."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="tt", email="tt@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="TT-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=1,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=2,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="tts", email="tts@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="P", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )

    def _make_appointment(self, weekday):
        day = _next_weekday(weekday)
        return Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(day, time(10, 0))
            ),
            reason="Test", booked_by=self.staff,
        )

    def _render(self):
        template = Template(
            "{% load billing_tags %}{% outstanding_bills_count %}"
        )
        return template.render(Context({})).strip()

    def test_zero_when_no_bills(self):
        Bill.objects.all().delete()
        self.assertEqual(self._render(), "0")

    def test_counts_finalized(self):
        Bill.objects.all().delete()
        appt = self._make_appointment(weekday=0)
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()

        self.assertEqual(self._render(), "1")

    def test_counts_partial(self):
        Bill.objects.all().delete()
        appt = self._make_appointment(weekday=0)
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        Payment.objects.create(
            bill=bill, amount=Decimal("200.00"),
            method="CASH", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PARTIAL")

        self.assertEqual(self._render(), "1")

    def test_does_not_count_paid(self):
        Bill.objects.all().delete()
        appt = self._make_appointment(weekday=0)
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        Payment.objects.create(
            bill=bill, amount=Decimal("500.00"),
            method="CASH", received_by=self.staff,
        )

        self.assertEqual(self._render(), "0")

    def test_does_not_count_draft(self):
        Bill.objects.all().delete()
        appt = self._make_appointment(weekday=0)
        Bill.objects.create(appointment=appt, patient=self.patient)
        # Draft, unfinalized — should not count

        self.assertEqual(self._render(), "0")

    def test_multiple_outstanding(self):
        Bill.objects.all().delete()
        for weekday in (0, 1, 2):
            appt = self._make_appointment(weekday=weekday)
            bill = Bill.objects.create(appointment=appt, patient=self.patient)
            BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
            bill.refresh_from_db()
            bill.finalize()

        self.assertEqual(self._render(), "3")