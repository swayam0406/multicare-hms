"""Tests for the Refund model."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import (
    Bill,
    BillItem,
    Payment,
    Refund,
    ServiceCatalog,
)
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class RefundSetupMixin:
    @classmethod
    def _setup(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="rd",
            email="rd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="RD-1",
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
            username="rs",
            email="rs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="ra",
            email="ra@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
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
            default_price=Decimal("1000.00"),
        )

    @classmethod
    def _paid_bill(cls):
        bill = Bill.objects.create(appointment=cls.appt, patient=cls.patient)
        BillItem.objects.create(bill=bill, service=cls.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        payment = Payment.objects.create(
            bill=bill,
            amount=Decimal("1000.00"),
            method="CASH",
            received_by=cls.staff,
        )
        return bill, payment


class RefundBasicsTests(RefundSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_create_refund(self):
        _, payment = self._paid_bill()
        r = Refund.objects.create(
            payment=payment,
            amount=Decimal("200.00"),
            method="CASH",
            reason="Item removed after billing",
            processed_by=self.admin,
        )
        self.assertEqual(r.amount, Decimal("200.00"))
        self.assertIsNotNone(r.processed_at)

    def test_refund_cannot_be_deleted(self):
        _, payment = self._paid_bill()
        r = Refund.objects.create(
            payment=payment,
            amount=Decimal("100.00"),
            method="CASH",
            reason="Test",
            processed_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            r.delete()

    def test_refund_is_immutable(self):
        _, payment = self._paid_bill()
        r = Refund.objects.create(
            payment=payment,
            amount=Decimal("100.00"),
            method="CASH",
            reason="Test",
            processed_by=self.admin,
        )
        r.amount = Decimal("200.00")
        with self.assertRaises(ValidationError):
            r.full_clean()


class RefundValidationTests(RefundSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_reason_required(self):
        _, payment = self._paid_bill()
        r = Refund(
            payment=payment,
            amount=Decimal("100.00"),
            method="CASH",
            reason="",
            processed_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_cannot_refund_pending_payment(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        pending = Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CARD",
            status="PENDING",
            received_by=self.staff,
        )
        r = Refund(
            payment=pending,
            amount=Decimal("100.00"),
            method="CARD",
            reason="Test",
            processed_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_refund_exceeding_payment_rejected(self):
        _, payment = self._paid_bill()
        r = Refund(
            payment=payment,
            amount=Decimal("1500.00"),
            method="CASH",
            reason="Excessive",
            processed_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_cumulative_refunds_capped(self):
        _, payment = self._paid_bill()
        Refund.objects.create(
            payment=payment,
            amount=Decimal("600.00"),
            method="CASH",
            reason="First",
            processed_by=self.admin,
        )
        # Second refund would total 700 + 600 = 1300 > 1000
        r = Refund(
            payment=payment,
            amount=Decimal("700.00"),
            method="CASH",
            reason="Second",
            processed_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            r.full_clean()


class RefundIntegrationTests(RefundSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_partial_refund_updates_bill_balance(self):
        bill, payment = self._paid_bill()
        self.assertEqual(bill.status, "PAID")
        self.assertEqual(bill.balance, Decimal("0.00"))

        Refund.objects.create(
            payment=payment,
            amount=Decimal("300.00"),
            method="CASH",
            reason="Test partial",
            processed_by=self.admin,
        )

        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("700.00"))
        self.assertEqual(bill.balance, Decimal("300.00"))
        self.assertEqual(bill.status, "PARTIAL")

    def test_full_refund_flips_payment_to_refunded(self):
        bill, payment = self._paid_bill()
        Refund.objects.create(
            payment=payment,
            amount=Decimal("1000.00"),
            method="CASH",
            reason="Full reversal",
            processed_by=self.admin,
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, "REFUNDED")

        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("0.00"))
        self.assertEqual(bill.balance, Decimal("1000.00"))
        self.assertEqual(bill.status, "FINALIZED")

    def test_two_partial_refunds_summing_to_full_flip_payment(self):
        bill, payment = self._paid_bill()
        Refund.objects.create(
            payment=payment,
            amount=Decimal("400.00"),
            method="CASH",
            reason="First",
            processed_by=self.admin,
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, "COMPLETED")

        Refund.objects.create(
            payment=payment,
            amount=Decimal("600.00"),
            method="CASH",
            reason="Second",
            processed_by=self.admin,
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REFUNDED")

    def test_payment_net_amount_reflects_refunds(self):
        _, payment = self._paid_bill()
        Refund.objects.create(
            payment=payment,
            amount=Decimal("300.00"),
            method="CASH",
            reason="Test",
            processed_by=self.admin,
        )
        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("300.00"))
        self.assertEqual(payment.net_amount, Decimal("700.00"))
