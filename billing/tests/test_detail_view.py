"""Tests for BillDetailView."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, Payment, Refund, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class BillDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="bdv",
            email="bdv@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="BDV-1",
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
            username="bdvs",
            email="bdvs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="bdva",
            email="bdva@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
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

    def _finalized_bill(cls_or_self):
        bill = Bill.objects.create(
            appointment=cls_or_self.appt,
            patient=cls_or_self.patient,
        )
        BillItem.objects.create(bill=bill, service=cls_or_self.cons, quantity=1)
        BillItem.objects.create(bill=bill, service=cls_or_self.lab, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        return bill

    def _url(self, bill):
        return reverse("billing:detail", kwargs={"bill_number": bill.bill_number})

    def test_anonymous_redirected(self):
        bill = self._finalized_bill()
        response = self.client.get(self._url(bill))
        self.assertEqual(response.status_code, 302)

    def test_patient_forbidden(self):
        bill = self._finalized_bill()
        pat_user = User.objects.create_user(
            username="pat",
            email="pat@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        self.client.login(username="pat", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view(self):
        bill = self._finalized_bill()
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, bill.bill_number)
        self.assertContains(response, "Alice")
        self.assertContains(response, "Consultation")

    def test_totals_displayed(self):
        bill = self._finalized_bill()
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        # 500 + 350 = 850
        self.assertContains(response, "₹850")

    def test_running_balance_after_partial_payment(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("400.00"),
            method="CASH",
            received_by=self.staff,
        )
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        # After ₹400 payment, running balance = 450
        rows = response.context["payment_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["running_balance"], Decimal("450.00"))

    def test_running_balance_multiple_payments(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("300.00"),
            method="CASH",
            received_by=self.staff,
        )
        Payment.objects.create(
            bill=bill,
            amount=Decimal("200.00"),
            method="UPI",
            received_by=self.staff,
        )
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        rows = response.context["payment_rows"]
        self.assertEqual(len(rows), 2)
        # After ₹300: balance = 550; after ₹200: balance = 350
        self.assertEqual(rows[0]["running_balance"], Decimal("550.00"))
        self.assertEqual(rows[1]["running_balance"], Decimal("350.00"))

    def test_refund_shown_under_payment(self):
        bill = self._finalized_bill()
        payment = Payment.objects.create(
            bill=bill,
            amount=Decimal("850.00"),
            method="CASH",
            received_by=self.staff,
        )
        Refund.objects.create(
            payment=payment,
            amount=Decimal("200.00"),
            method="CASH",
            reason="Test refund",
            processed_by=self.admin,
        )
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertContains(response, "Test refund")
        self.assertContains(response, "−₹200")

    def test_action_flags_for_draft(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertTrue(response.context["can_add_items"])
        self.assertTrue(response.context["can_finalize"])
        self.assertFalse(response.context["can_record_payment"])

    def test_action_flags_for_finalized(self):
        bill = self._finalized_bill()
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertFalse(response.context["can_add_items"])
        self.assertFalse(response.context["can_finalize"])
        self.assertTrue(response.context["can_record_payment"])

    def test_action_flags_for_paid(self):
        bill = self._finalized_bill()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("850.00"),
            method="CASH",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(self._url(bill))
        self.assertFalse(response.context["can_record_payment"])

    def test_404_for_nonexistent_bill(self):
        self.client.login(username="bdvs", password="pass1234")
        response = self.client.get(
            reverse("billing:detail", kwargs={"bill_number": "INV-9999-99999"})
        )
        self.assertEqual(response.status_code, 404)
