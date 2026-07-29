"""Tests for Bill and BillItem."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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


class BillingSetupMixin:
    @classmethod
    def _setup_common(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="bd",
            email="bd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="BD-1",
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
            username="bs",
            email="bs@t.local",
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
        cls.cbc = ServiceCatalog.objects.create(
            code="LAB-CBC",
            name="CBC",
            category="LABORATORY",
            default_price=Decimal("350.00"),
        )


class BillCreationTests(BillingSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup_common()

    def test_bill_number_auto_generated(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        self.assertTrue(bill.bill_number.startswith("INV-"))
        self.assertIn(str(timezone.now().year), bill.bill_number)

    def test_bill_number_sequence(self):
        b1 = Bill.objects.create(appointment=self.appt, patient=self.patient)

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
            reason="Second",
            booked_by=self.staff,
        )
        b2 = Bill.objects.create(appointment=appt2, patient=self.patient)

        seq1 = int(b1.bill_number.split("-")[-1])
        seq2 = int(b2.bill_number.split("-")[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_one_bill_per_appointment(self):
        Bill.objects.create(appointment=self.appt, patient=self.patient)
        with self.assertRaises(IntegrityError):
            Bill.objects.create(appointment=self.appt, patient=self.patient)

    def test_bill_starts_as_draft(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        self.assertEqual(bill.status, "DRAFT")
        self.assertEqual(bill.total, Decimal("0.00"))


class BillItemTests(BillingSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup_common()
        cls.bill = Bill.objects.create(appointment=cls.appt, patient=cls.patient)

    def test_item_defaults_price_from_service(self):
        item = BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.assertEqual(item.unit_price, Decimal("500.00"))

    def test_item_defaults_description_from_service(self):
        item = BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.assertEqual(item.description, "Consultation")

    def test_line_total_computed(self):
        item = BillItem.objects.create(
            bill=self.bill,
            service=self.cons,
            quantity=3,
        )
        self.assertEqual(item.line_total, Decimal("1500.00"))

    def test_bill_subtotal_rolls_up(self):
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        BillItem.objects.create(bill=self.bill, service=self.cbc, quantity=1)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.subtotal, Decimal("850.00"))
        self.assertEqual(self.bill.total, Decimal("850.00"))

    def test_deleting_item_rolls_up(self):
        i1 = BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        BillItem.objects.create(bill=self.bill, service=self.cbc, quantity=1)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.subtotal, Decimal("850.00"))

        i1.delete()
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.subtotal, Decimal("350.00"))

    def test_quantity_zero_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BillItem.objects.create(bill=self.bill, service=self.cons, quantity=0)

    def test_service_protected_from_deletion(self):
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.cons.delete()


class BillTotalsTests(BillingSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup_common()

    def setUp(self):
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        BillItem.objects.create(bill=self.bill, service=self.cbc, quantity=1)
        self.bill.refresh_from_db()

    def test_no_tax_no_discount(self):
        self.assertEqual(self.bill.subtotal, Decimal("850.00"))
        self.assertEqual(self.bill.total, Decimal("850.00"))

    def test_flat_discount_applied(self):
        self.bill.discount_amount = Decimal("100.00")
        self.bill.recompute_totals()
        self.assertEqual(self.bill.total, Decimal("750.00"))

    def test_tax_applied_on_discounted_amount(self):
        self.bill.discount_amount = Decimal("50.00")
        self.bill.tax_rate = Decimal("5.00")
        self.bill.recompute_totals()
        self.assertEqual(self.bill.tax_amount, Decimal("40.00"))
        self.assertEqual(self.bill.total, Decimal("840.00"))

    def test_discount_larger_than_subtotal(self):
        self.bill.discount_amount = Decimal("1000.00")
        self.bill.recompute_totals()
        self.assertEqual(self.bill.total, Decimal("0.00"))

    def test_paid_amount_zero_without_payments(self):
        self.assertEqual(self.bill.paid_amount, Decimal("0.00"))

    def test_balance_equals_total_without_payments(self):
        self.assertEqual(self.bill.balance, self.bill.total)


class BillStateMachineTests(BillingSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup_common()

    def test_can_edit_items_only_in_draft(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        self.assertTrue(bill.can_edit_items())

        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.finalize()
        self.assertFalse(bill.can_edit_items())

    def test_finalize_without_items_fails(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        with self.assertRaises(ValidationError):
            bill.finalize()

    def test_finalize_updates_status_and_timestamp(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.finalize(user=self.staff)
        self.assertEqual(bill.status, "FINALIZED")
        self.assertIsNotNone(bill.finalized_at)
        self.assertEqual(bill.finalized_by, self.staff)

    def test_finalize_twice_rejected(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.finalize()
        with self.assertRaises(ValidationError):
            bill.finalize()
