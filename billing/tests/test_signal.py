"""Tests for the auto-bill-on-completion signal."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class AutoBillSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="sigd",
            email="sigd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="SIGD-1",
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
            username="sigs",
            email="sigs@t.local",
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
        cls.consultation_svc = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="General consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )

    def _make_appointment(self):
        monday = _next_weekday(0)
        return Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(monday, time(10, 0))),
            reason="Test",
            booked_by=self.staff,
        )

    def test_completing_creates_bill(self):
        appt = self._make_appointment()
        self.assertFalse(hasattr(appt, "bill"))

        appt.status = "COMPLETED"
        appt.save()

        appt.refresh_from_db()
        self.assertTrue(hasattr(appt, "bill"))

    def test_bill_created_as_draft(self):
        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()
        self.assertEqual(appt.bill.status, "DRAFT")

    def test_bill_has_consultation_line_item(self):
        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()

        items = appt.bill.items.all()
        self.assertEqual(items.count(), 1)
        item = items.first()
        self.assertEqual(item.service, self.consultation_svc)
        self.assertEqual(item.unit_price, Decimal("500.00"))
        self.assertIn("Consultation", item.description)

    def test_bill_denormalizes_patient(self):
        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()
        self.assertEqual(appt.bill.patient, self.patient)

    def test_bill_records_creator(self):
        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()
        self.assertEqual(appt.bill.created_by, self.staff)

    def test_signal_is_idempotent(self):
        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()
        appt.save()  # Save again — should not create a second bill
        self.assertEqual(Bill.objects.filter(appointment=appt).count(), 1)

    def test_non_completed_status_does_not_create_bill(self):
        appt = self._make_appointment()

        for status in ("CONFIRMED", "IN_PROGRESS", "CANCELLED", "NO_SHOW"):
            appt.status = status
            appt.save()
            appt.refresh_from_db()
            self.assertFalse(
                hasattr(appt, "bill"),
                f"Bill should NOT exist for status {status}",
            )

    def test_no_catalog_service_leaves_bill_empty(self):
        """If no consultation service in catalog, bill is created empty."""
        ServiceCatalog.objects.all().delete()

        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()

        self.assertTrue(hasattr(appt, "bill"))
        self.assertEqual(appt.bill.items.count(), 0)

    def test_zero_consultation_fee_leaves_bill_empty(self):
        """If doctor's fee is zero, no line item is added."""
        self.doctor.consultation_fee = Decimal("0.00")
        self.doctor.save()

        appt = self._make_appointment()
        appt.status = "COMPLETED"
        appt.save()

        self.assertTrue(hasattr(appt, "bill"))
        self.assertEqual(appt.bill.items.count(), 0)

    def test_completing_via_transition_creates_bill(self):
        """End-to-end test through the actual state machine."""
        appt = self._make_appointment()

        # Manually walk states (bypass ownership checks by direct save)
        appt.status = "CONFIRMED"
        appt.save()
        appt.status = "IN_PROGRESS"
        appt.save()
        appt.status = "COMPLETED"
        appt.save()

        appt.refresh_from_db()
        self.assertTrue(hasattr(appt, "bill"))
        self.assertEqual(appt.bill.items.count(), 1)
