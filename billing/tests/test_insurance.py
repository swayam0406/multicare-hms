"""Tests for InsuranceClaim model + state machine."""

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
    InsuranceClaim,
    ServiceCatalog,
)
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class InsuranceSetupMixin:
    @classmethod
    def _setup(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="id",
            email="id@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="ID-1",
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
            username="is",
            email="is@t.local",
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
        cls.mri = ServiceCatalog.objects.create(
            code="IMG-MRI",
            name="MRI",
            category="IMAGING",
            default_price=Decimal("5000.00"),
        )

    @classmethod
    def _finalized_bill(cls, extra_items=True):
        bill = Bill.objects.create(appointment=cls.appt, patient=cls.patient)
        BillItem.objects.create(bill=bill, service=cls.cons, quantity=1)
        if extra_items:
            BillItem.objects.create(bill=bill, service=cls.mri, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        return bill


class InsuranceClaimBasicsTests(InsuranceSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_create_claim_defaults(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="Star Health",
            policy_number="POL-12345",
            amount_claimed=Decimal("3000.00"),
        )
        self.assertEqual(claim.status, "SUBMITTED")
        self.assertEqual(claim.amount_approved, Decimal("0.00"))
        self.assertIsNone(claim.approved_at)
        self.assertIsNone(claim.linked_payment)

    def test_multiple_claims_per_bill_allowed(self):
        bill = self._finalized_bill()
        InsuranceClaim.objects.create(
            bill=bill,
            provider="Primary Ins",
            policy_number="P1",
            amount_claimed=Decimal("2000.00"),
        )
        InsuranceClaim.objects.create(
            bill=bill,
            provider="Secondary Ins",
            policy_number="P2",
            amount_claimed=Decimal("1000.00"),
        )
        self.assertEqual(bill.insurance_claims.count(), 2)


class InsuranceApprovalTests(InsuranceSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_approve_claim(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="Star Health",
            policy_number="POL-12345",
            amount_claimed=Decimal("3000.00"),
        )
        claim.mark_approved(Decimal("2500.00"), user=self.staff)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "APPROVED")
        self.assertEqual(claim.amount_approved, Decimal("2500.00"))
        self.assertIsNotNone(claim.approved_at)

    def test_cannot_approve_more_than_claimed(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        with self.assertRaises(ValidationError):
            claim.mark_approved(Decimal("2000.00"))

    def test_cannot_approve_negative(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        with self.assertRaises(ValidationError):
            claim.mark_approved(Decimal("-100.00"))

    def test_cannot_approve_non_submitted_claim(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        claim.mark_approved(Decimal("800.00"))
        with self.assertRaises(ValidationError):
            claim.mark_approved(Decimal("900.00"))


class InsuranceRejectionTests(InsuranceSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_reject_claim(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        claim.mark_rejected("Policy inactive")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "REJECTED")
        self.assertEqual(claim.rejection_reason, "Policy inactive")
        self.assertEqual(claim.amount_approved, Decimal("0.00"))

    def test_rejection_requires_reason(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        with self.assertRaises(ValidationError):
            claim.mark_rejected("")


class InsurancePaymentTests(InsuranceSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def test_mark_paid_creates_linked_payment(self):
        bill = self._finalized_bill()
        # Total should be 5500
        self.assertEqual(bill.total, Decimal("5500.00"))

        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="Star Health",
            policy_number="POL-12345",
            amount_claimed=Decimal("5000.00"),
        )
        claim.mark_approved(Decimal("4000.00"))
        claim.mark_paid(received_by=self.staff)

        claim.refresh_from_db()
        self.assertEqual(claim.status, "PAID")
        self.assertIsNotNone(claim.linked_payment)
        self.assertEqual(claim.linked_payment.amount, Decimal("4000.00"))
        self.assertEqual(claim.linked_payment.method, "INSURANCE")
        self.assertEqual(claim.linked_payment.status, "COMPLETED")

    def test_paid_claim_updates_bill(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("5500.00"),
        )
        claim.mark_approved(Decimal("5500.00"))
        claim.mark_paid()

        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")

    def test_partial_insurance_leaves_balance(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("3000.00"),
        )
        claim.mark_approved(Decimal("3000.00"))
        claim.mark_paid()

        bill.refresh_from_db()
        self.assertEqual(bill.status, "PARTIAL")
        self.assertEqual(bill.balance, Decimal("2500.00"))

    def test_cannot_pay_non_approved_claim(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("1000.00"),
        )
        with self.assertRaises(ValidationError):
            claim.mark_paid()

    def test_mark_paid_is_idempotent(self):
        bill = self._finalized_bill()
        claim = InsuranceClaim.objects.create(
            bill=bill,
            provider="X",
            policy_number="P",
            amount_claimed=Decimal("3000.00"),
        )
        claim.mark_approved(Decimal("3000.00"))
        claim.mark_paid()
        first_payment = claim.linked_payment

        # Second call — cannot go PAID → PAID via mark_paid()
        with self.assertRaises(ValidationError):
            claim.mark_paid()

        claim.refresh_from_db()
        self.assertEqual(claim.linked_payment, first_payment)
