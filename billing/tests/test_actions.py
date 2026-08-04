"""Tests for the billing action views."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import (
    Bill,
    BillItem,
    ServiceCatalog,
)
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class BillActionsSetupMixin:
    @classmethod
    def _setup(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="ba",
            email="ba@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="BA-1",
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
            username="bas",
            email="bas@t.local",
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
        cls.lab = ServiceCatalog.objects.create(
            code="LAB-CBC",
            name="CBC",
            category="LABORATORY",
            default_price=Decimal("350.00"),
        )


class ItemAddDeleteTests(BillActionsSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def setUp(self):
        self.client.login(username="bas", password="pass1234")
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)

    def _add_url(self):
        return reverse("billing:item_add", kwargs={"bill_number": self.bill.bill_number})

    def test_add_item_success(self):
        response = self.client.post(
            self._add_url(),
            {
                "service": str(self.cons.pk),
                "quantity": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 1)
        self.assertEqual(self.bill.subtotal, Decimal("500.00"))

    def test_add_item_with_quantity(self):
        self.client.post(
            self._add_url(),
            {
                "service": str(self.cons.pk),
                "quantity": "3",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.first().quantity, 3)
        self.assertEqual(self.bill.subtotal, Decimal("1500.00"))

    def test_add_item_with_price_override(self):
        self.client.post(
            self._add_url(),
            {
                "service": str(self.cons.pk),
                "quantity": "1",
                "unit_price": "300.00",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.first().unit_price, Decimal("300.00"))

    def test_add_item_missing_service_rejected(self):
        self.client.post(self._add_url(), {"quantity": "1"})
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 0)

    def test_add_item_quantity_zero_rejected(self):
        self.client.post(
            self._add_url(),
            {
                "service": str(self.cons.pk),
                "quantity": "0",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 0)

    def test_add_item_rejected_on_finalized_bill(self):
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.bill.refresh_from_db()
        self.bill.finalize()

        self.client.post(
            self._add_url(),
            {
                "service": str(self.lab.pk),
                "quantity": "1",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 1)

    def test_delete_item_success(self):
        item = BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        url = reverse(
            "billing:item_delete",
            kwargs={
                "bill_number": self.bill.bill_number,
                "item_pk": item.pk,
            },
        )
        self.client.post(url)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 0)

    def test_delete_rejected_on_finalized(self):
        item = BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.bill.refresh_from_db()
        self.bill.finalize()
        url = reverse(
            "billing:item_delete",
            kwargs={
                "bill_number": self.bill.bill_number,
                "item_pk": item.pk,
            },
        )
        self.client.post(url)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), 1)


class FinalizeTests(BillActionsSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def setUp(self):
        self.client.login(username="bas", password="pass1234")
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)

    def _url(self):
        return reverse("billing:finalize", kwargs={"bill_number": self.bill.bill_number})

    def test_finalize_empty_bill_rejected(self):
        self.client.post(self._url())
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "DRAFT")

    def test_finalize_success(self):
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.client.post(self._url())
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "FINALIZED")


class PaymentActionTests(BillActionsSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def setUp(self):
        self.client.login(username="bas", password="pass1234")
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.bill.refresh_from_db()
        self.bill.finalize()

    def _url(self):
        return reverse("billing:payment_add", kwargs={"bill_number": self.bill.bill_number})

    def test_record_full_payment(self):
        self.client.post(
            self._url(),
            {
                "amount": "500.00",
                "method": "CASH",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "PAID")

    def test_record_partial_payment(self):
        self.client.post(
            self._url(),
            {
                "amount": "200.00",
                "method": "UPI",
                "reference": "UPI-TXN-1",
            },
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "PARTIAL")
        self.assertEqual(self.bill.balance, Decimal("300.00"))

    def test_payment_zero_rejected(self):
        self.client.post(
            self._url(),
            {
                "amount": "0",
                "method": "CASH",
            },
        )
        self.assertEqual(self.bill.payments.count(), 0)

    def test_overpayment_rejected(self):
        self.client.post(
            self._url(),
            {
                "amount": "9999",
                "method": "CASH",
            },
        )
        self.assertEqual(self.bill.payments.count(), 0)

    def test_payment_on_draft_bill_rejected(self):
        Bill.objects.create(appointment=self.appt, patient=self.patient)
        # Whoops — appointment is OneToOne. Delete existing and try again with fresh appt.
        # Instead, just test the guard: reset our bill to DRAFT-like unfinalized state.
        # Simpler: create a separate appt+bill for isolation.
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
        url = reverse("billing:payment_add", kwargs={"bill_number": bill2.bill_number})
        self.client.post(url, {"amount": "100", "method": "CASH"})
        self.assertEqual(bill2.payments.count(), 0)


class InsuranceActionTests(BillActionsSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def setUp(self):
        self.client.login(username="bas", password="pass1234")
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=self.bill, service=self.cons, quantity=1)
        self.bill.refresh_from_db()
        self.bill.finalize()

    def _url(self):
        return reverse("billing:insurance_add", kwargs={"bill_number": self.bill.bill_number})

    def test_file_claim_success(self):
        self.client.post(
            self._url(),
            {
                "provider": "Star Health",
                "policy_number": "POL-123",
                "amount_claimed": "500.00",
            },
        )
        self.assertEqual(self.bill.insurance_claims.count(), 1)
        claim = self.bill.insurance_claims.first()
        self.assertEqual(claim.provider, "Star Health")

    def test_missing_provider_rejected(self):
        self.client.post(
            self._url(),
            {
                "policy_number": "POL-123",
                "amount_claimed": "500.00",
            },
        )
        self.assertEqual(self.bill.insurance_claims.count(), 0)

    def test_negative_amount_rejected(self):
        self.client.post(
            self._url(),
            {
                "provider": "X",
                "policy_number": "P",
                "amount_claimed": "-100",
            },
        )
        self.assertEqual(self.bill.insurance_claims.count(), 0)


class RBACTests(BillActionsSetupMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._setup()

    def setUp(self):
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)

    def test_anonymous_redirected(self):
        response = self.client.post(
            reverse("billing:item_add", kwargs={"bill_number": self.bill.bill_number}),
        )
        self.assertEqual(response.status_code, 302)

    def test_patient_forbidden(self):
        User.objects.create_user(
            username="pat",
            email="pat@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        self.client.login(username="pat", password="pass1234")
        response = self.client.post(
            reverse("billing:item_add", kwargs={"bill_number": self.bill.bill_number}),
        )
        self.assertEqual(response.status_code, 403)

    def test_get_not_allowed(self):
        self.client.login(username="bas", password="pass1234")
        response = self.client.get(
            reverse("billing:item_add", kwargs={"bill_number": self.bill.bill_number}),
        )
        self.assertEqual(response.status_code, 405)
