"""Tests for cached template tags."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase
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


class CachedOutstandingBillsTagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="ct_doc", email="ctd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="CT-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="ct_staff", email="cts@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.patient = Patient.objects.create(
            first_name="P", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        cls.cons_svc = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )

    def setUp(self):
        # Isolate the cache between tests
        cache.clear()

    def _make_finalized_bill(self, weekday):
        DoctorAvailability.objects.get_or_create(
            doctor=self.doctor, weekday=weekday,
            defaults={"start_time": time(9, 0), "end_time": time(12, 0)},
        )
        appt = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(_next_weekday(weekday), time(10, 0))
            ),
            reason="T", booked_by=self.staff,
        )
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons_svc, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        return bill

    def _render(self):
        template = Template(
            "{% load billing_tags %}{% outstanding_bills_count %}"
        )
        return template.render(Context({})).strip()

    def test_zero_when_no_bills(self):
        self.assertEqual(self._render(), "0")

    def test_counts_finalized_only(self):
        self._make_finalized_bill(0)
        self.assertEqual(self._render(), "1")

    def test_result_is_cached(self):
        self._make_finalized_bill(0)
        first = self._render()
        self.assertEqual(first, "1")

        # Create another bill — count would rise to 2 without cache
        self._make_finalized_bill(1)

        # Cached: still returns 1
        cached = self._render()
        self.assertEqual(cached, "1")

        # Clear cache: now it reflects new value
        cache.clear()
        self.assertEqual(self._render(), "2")


class CachedLowStockTagTests(TestCase):
    def setUp(self):
        cache.clear()

    def _render(self):
        template = Template(
            "{% load pharmacy_tags %}{% low_stock_count %}"
        )
        return template.render(Context({})).strip()

    def test_zero_when_no_inventory(self):
        self.assertEqual(self._render(), "0")

    def test_caches_between_calls(self):
        from medical_records.models import MedicationCatalog
        from pharmacy.models import InventoryItem

        med = MedicationCatalog.objects.create(
            name="Test", strength="10mg", form="TABLET",
        )
        InventoryItem.objects.create(
            medication=med, quantity_on_hand=5, reorder_threshold=10,
        )
        first = self._render()
        self.assertEqual(first, "1")

        # Change to no longer low-stock
        InventoryItem.objects.filter(medication=med).update(quantity_on_hand=100)

        # Cache still says 1
        self.assertEqual(self._render(), "1")

        # Clear: refreshes
        cache.clear()
        self.assertEqual(self._render(), "0")
