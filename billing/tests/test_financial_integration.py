"""End-to-end financial integration tests — payment + refund + insurance."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import (
    Bill, BillItem, InsuranceClaim, Payment, Refund, ServiceCatalog,
)
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class FinancialSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="fi", email="fi@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="FI-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="fis", email="fis@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="fia", email="fia@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )
        cls.patient = Patient.objects.create(
            first_name="P", last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE, phone="9876543210",
            registered_by=cls.staff,
        )
        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient, doctor=cls.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(monday, time(10, 0))
            ),
            reason="Test", booked_by=cls.staff,
        )
        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )
        cls.mri = ServiceCatalog.objects.create(
            code="IMG-MRI", name="MRI",
            category="IMAGING", default_price=Decimal("7000.00"),
        )

    def _finalized_bill(self, total_expected):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        BillItem.objects.create(bill=bill, service=self.mri, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        self.assertEqual(bill.total, total_expected)
        return bill


class PaymentRefundLedgerTests(FinancialSetup):
    """The tricky area — partial payment, then partial refund on that payment."""

    def test_partial_refund_of_completed_payment_reduces_bill_paid(self):
        """
        Bill: ₹7500. Payment: ₹3000. Refund: ₹1000.
        Net paid = ₹2000. Balance = ₹5500.
        """
        bill = self._finalized_bill(Decimal("7500.00"))
        payment = Payment.objects.create(
            bill=bill, amount=Decimal("3000.00"),
            method="CASH", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("3000.00"))
        self.assertEqual(bill.status, "PARTIAL")

        Refund.objects.create(
            payment=payment, amount=Decimal("1000.00"),
            method="CASH", reason="Duplicate charge",
            processed_by=self.admin,
        )

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("1000.00"))
        self.assertEqual(payment.net_amount, Decimal("2000.00"))
        # Payment stays COMPLETED (not fully refunded)
        self.assertEqual(payment.status, "COMPLETED")

        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("2000.00"))
        self.assertEqual(bill.balance, Decimal("5500.00"))
        self.assertEqual(bill.status, "PARTIAL")

    def test_full_payment_then_full_refund_moves_bill_back_to_finalized(self):
        bill = self._finalized_bill(Decimal("7500.00"))
        payment = Payment.objects.create(
            bill=bill, amount=Decimal("7500.00"),
            method="UPI", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")

        Refund.objects.create(
            payment=payment, amount=Decimal("7500.00"),
            method="UPI", reason="Bill voided",
            processed_by=self.admin,
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, "REFUNDED")
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("0.00"))
        self.assertEqual(bill.balance, Decimal("7500.00"))
        self.assertEqual(bill.status, "FINALIZED")

    def test_multiple_payments_and_refunds_ledger_correct(self):
        """
        Payments: ₹3000 + ₹2000 + ₹2500 = ₹7500 → PAID.
        Refund the ₹2500 → PARTIAL, balance = ₹2500.
        """
        bill = self._finalized_bill(Decimal("7500.00"))
        Payment.objects.create(
            bill=bill, amount=Decimal("3000.00"),
            method="CASH", received_by=self.staff,
        )
        Payment.objects.create(
            bill=bill, amount=Decimal("2000.00"),
            method="UPI", received_by=self.staff,
        )
        p3 = Payment.objects.create(
            bill=bill, amount=Decimal("2500.00"),
            method="CARD", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")

        Refund.objects.create(
            payment=p3, amount=Decimal("2500.00"),
            method="CARD", reason="Card chargeback",
            processed_by=self.admin,
        )

        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal("5000.00"))
        self.assertEqual(bill.balance, Decimal("2500.00"))
        self.assertEqual(bill.status, "PARTIAL")


class InsuranceEndToEndTests(FinancialSetup):
    """From claim submission through payment → bill status."""

    def test_insurance_paid_fully_marks_bill_paid(self):
        bill = self._finalized_bill(Decimal("7500.00"))

        claim = InsuranceClaim.objects.create(
            bill=bill, provider="Star Health",
            policy_number="POL-1", amount_claimed=Decimal("8000.00"),
        )
        claim.mark_approved(Decimal("7500.00"))
        claim.mark_paid(received_by=self.staff)

        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")
        self.assertEqual(bill.paid_amount, Decimal("7500.00"))

        # Linked payment created + attached
        self.assertIsNotNone(claim.linked_payment)
        self.assertEqual(claim.linked_payment.method, "INSURANCE")

    def test_insurance_partial_plus_cash_pays_bill(self):
        bill = self._finalized_bill(Decimal("7500.00"))

        # Insurance covers ₹5000 of ₹7500
        claim = InsuranceClaim.objects.create(
            bill=bill, provider="Star Health",
            policy_number="POL-1", amount_claimed=Decimal("5000.00"),
        )
        claim.mark_approved(Decimal("5000.00"))
        claim.mark_paid()

        bill.refresh_from_db()
        self.assertEqual(bill.status, "PARTIAL")
        self.assertEqual(bill.balance, Decimal("2500.00"))

        # Patient pays the remaining ₹2500 in cash
        Payment.objects.create(
            bill=bill, amount=Decimal("2500.00"),
            method="CASH", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")

    def test_insurance_approval_capped_at_balance(self):
        """Approved amount > outstanding balance? Insurance payment capped."""
        bill = self._finalized_bill(Decimal("7500.00"))

        # Patient pays ₹5000 first
        Payment.objects.create(
            bill=bill, amount=Decimal("5000.00"),
            method="CASH", received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.balance, Decimal("2500.00"))

        # Insurance approves ₹4000, more than remaining balance
        claim = InsuranceClaim.objects.create(
            bill=bill, provider="Star Health",
            policy_number="POL-1", amount_claimed=Decimal("4000.00"),
        )
        claim.mark_approved(Decimal("4000.00"))
        claim.mark_paid()

        # Payment should be capped at ₹2500 (the remaining balance)
        claim.refresh_from_db()
        self.assertEqual(claim.linked_payment.amount, Decimal("2500.00"))

        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")
        self.assertEqual(bill.balance, Decimal("0.00"))


class BillNumberSequenceTests(FinancialSetup):
    """Verify sequence handling under quick concurrent creation."""

    def test_sequential_bill_numbers(self):
        # Reset any existing bills for a clean run
        Bill.objects.all().delete()
        DoctorAvailability.objects.create(
            doctor=self.doctor, weekday=1,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b1 = Bill.objects.create(appointment=self.appt, patient=self.patient)

        # Second appointment
        tuesday = _next_weekday(1)
        appt2 = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(tuesday, time(10, 0))
            ),
            reason="Second", booked_by=self.staff,
        )
        b2 = Bill.objects.create(appointment=appt2, patient=self.patient)

        seq1 = int(b1.bill_number.split("-")[-1])
        seq2 = int(b2.bill_number.split("-")[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_bill_number_format(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        parts = bill.bill_number.split("-")
        self.assertEqual(parts[0], "INV")
        self.assertEqual(len(parts[1]), 4)  # year
        self.assertEqual(len(parts[2]), 5)  # zero-padded 5-digit sequence