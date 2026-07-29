"""Tests for MyBillsView."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
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


class MyBillsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="mbd",
            email="mbd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="MB-1",
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
            username="mbs",
            email="mbs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )

        # Patient user + linked Patient
        cls.patient_user = User.objects.create_user(
            username="mbp",
            email="mbp@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        cls.patient = Patient.objects.create(
            first_name="Alice",
            last_name="Anderson",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.FEMALE,
            phone="9876543210",
            registered_by=cls.staff,
            user=cls.patient_user,
        )

        # Orphan patient user (no Patient linked)
        cls.orphan = User.objects.create_user(
            username="orphan_mb",
            email="o@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )

        # Admin (should be forbidden)
        cls.admin = User.objects.create_user(
            username="mba",
            email="a@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )

        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="Consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )

    def _url(self):
        return reverse("patients:my_bills")

    def _make_appointment_and_bill(self, weekday=0):
        DoctorAvailability.objects.get_or_create(
            doctor=self.doctor,
            weekday=weekday,
            defaults={"start_time": time(9, 0), "end_time": time(12, 0)},
        )
        day = _next_weekday(weekday)
        appt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(day, time(10, 0))),
            reason="Test",
            booked_by=self.staff,
        )
        bill = Bill.objects.create(appointment=appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        return bill

    # ---------- Access ----------

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_staff_forbidden(self):
        self.client.login(username="mba", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_orphan_patient_gets_404(self):
        self.client.login(username="orphan_mb", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    def test_patient_can_access(self):
        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # ---------- Content ----------

    def test_empty_state(self):
        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["bill_count"], 0)
        self.assertEqual(response.context["total_billed"], Decimal("0.00"))
        self.assertContains(response, "No bills yet")

    def test_bill_displayed(self):
        bill = self._make_appointment_and_bill()
        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["bill_count"], 1)
        self.assertContains(response, bill.bill_number)

    def test_totals_sum_correctly(self):
        b1 = self._make_appointment_and_bill(weekday=0)
        b2 = self._make_appointment_and_bill(weekday=1)
        b1.finalize()
        b2.finalize()
        Payment.objects.create(
            bill=b1,
            amount=Decimal("300.00"),
            method="CASH",
            received_by=self.staff,
        )

        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.context["total_billed"], Decimal("1000.00"))
        self.assertEqual(response.context["total_paid"], Decimal("300.00"))
        self.assertEqual(response.context["total_outstanding"], Decimal("700.00"))

    def test_cancelled_bill_excluded_from_totals(self):
        b1 = self._make_appointment_and_bill(weekday=0)
        b1.finalize()
        b2 = self._make_appointment_and_bill(weekday=1)
        # Directly cancel b2
        b2.status = "CANCELLED"
        b2.save()

        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        # Only b1's ₹500 counted
        self.assertEqual(response.context["total_billed"], Decimal("500.00"))

    def test_patient_cannot_see_other_patients_bills(self):
        # Create another patient with their own bill
        other_user = User.objects.create_user(
            username="mbp2",
            email="mbp2@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        other_patient = Patient.objects.create(
            first_name="Other",
            last_name="Person",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.FEMALE,
            phone="9876543211",
            registered_by=self.staff,
            user=other_user,
        )
        DoctorAvailability.objects.get_or_create(
            doctor=self.doctor,
            weekday=1,
            defaults={"start_time": time(9, 0), "end_time": time(12, 0)},
        )
        tuesday = _next_weekday(1)
        appt = Appointment.objects.create(
            patient=other_patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(tuesday, time(10, 0))),
            reason="Other",
            booked_by=self.staff,
        )
        Bill.objects.create(appointment=appt, patient=other_patient)

        self.client.login(username="mbp", password="pass1234")
        response = self.client.get(self._url())
        # None of the "other" patient's bills should be visible
        self.assertEqual(response.context["bill_count"], 0)
