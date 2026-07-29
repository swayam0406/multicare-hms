"""Tests for the Payment model + partial-payment logic."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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


class PaymentSetupMixin:
    @classmethod
    def _setup(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="pd",
            email="pd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="PD-1",
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
            username="ps",
            email="ps@t.local",
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

    @classmethod
    def _finalized_bill(cls):
        bill = Bill.objects.create(appointment=cls.appt, patient=cls.patient)
        BillItem.objects.create(bill=bill, service=cls.cons, quantity=1)
        BillItem.objects.create(bill=bill, service=cls.cbc, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        return bill


class PaymentBasicsTests(PaymentSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_create_payment_default_completed(self):
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        self.assertEqual(pay.status, "COMPLETED")

    def test_received_at_auto_set(self):
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        self.assertIsNotNone(pay.received_at)

    def test_payment_cannot_be_deleted(self):
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            pay.delete()


class PaymentBillIntegrationTests(PaymentSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_partial_payment_moves_bill_to_partial(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("400.00"),
            method="CASH",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PARTIAL")

    def test_full_payment_moves_bill_to_paid(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("850.00"),
            method="UPI",
            reference="UPI-TXN-123",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")
        self.assertEqual(bill.paid_amount, Decimal("850.00"))
        self.assertEqual(bill.balance, Decimal("0.00"))

    def test_multiple_partial_payments_add_up(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("400.00"),
            method="CASH",
            received_by=self.staff,
        )
        Payment.objects.create(
            bill=bill,
            amount=Decimal("450.00"),
            method="UPI",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("850.00"))
        self.assertEqual(bill.status, "PAID")

    def test_pending_payment_does_not_count_toward_paid(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CARD",
            status="PENDING",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("0.00"))
        self.assertEqual(bill.status, "FINALIZED")


class PaymentValidationTests(PaymentSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_payment_on_draft_bill_rejected(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        # No items, not finalized — DRAFT
        pay = Payment(
            bill=bill,
            amount=Decimal("100.00"),
            method="CASH",
            received_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            pay.full_clean()

    def test_overpayment_rejected(self):
        bill = self._finalized_bill()
        pay = Payment(
            bill=bill,
            amount=Decimal("9999.00"),
            method="CASH",
            received_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            pay.full_clean()


class PaymentImmutabilityTests(PaymentSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_cannot_change_amount_after_completed(self):
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        pay.amount = Decimal("400.00")
        with self.assertRaises(ValidationError):
            pay.full_clean()

    def test_cannot_change_method_after_completed(self):
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        pay.method = "UPI"
        with self.assertRaises(ValidationError):
            pay.full_clean()

    def test_can_edit_reference_and_notes(self):
        """Non-financial fields can still be updated for record-keeping."""
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="UPI",
            received_by=self.staff,
        )
        pay.reference = "UPI-TXN-999"
        pay.notes = "Reference updated after checking bank statement"
        pay.full_clean()  # Should NOT raise
        pay.save()
        pay.refresh_from_db()
        self.assertEqual(pay.reference, "UPI-TXN-999")

    def test_pending_payment_can_be_modified(self):
        """Pending payments can be updated (e.g., card auth arriving late)."""
        bill = self._finalized_bill()
        pay = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CARD",
            status="PENDING",
            received_by=self.staff,
        )
        pay.amount = Decimal("450.00")
        pay.full_clean()  # Should NOT raise
        pay.save()
        pay.refresh_from_db()
        self.assertEqual(pay.amount, Decimal("450.00"))
