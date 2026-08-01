"""Tests for BillAdmin bulk actions."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.admin import BillAdmin
from billing.models import Bill, BillItem, Payment, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class BillAdminBulkActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="baa",
            email="baa@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="BAA-1",
            specialty="x",
            qualifications="MBBS",
            consultation_fee=Decimal("500.00"),
        )
        for weekday in (0, 1, 2):
            DoctorAvailability.objects.create(
                doctor=cls.doctor,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(12, 0),
            )
        cls.staff = User.objects.create_user(
            username="baas",
            email="baas@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="baaa",
            email="baaa@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        cls.patient = Patient.objects.create(
            first_name="P",
            last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543210",
            registered_by=cls.staff,
        )
        cls.cons = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="Consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )

    def _paid_bill(self, weekday):
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
        bill.finalize()
        Payment.objects.create(
            bill=bill,
            amount=Decimal("500.00"),
            method="CASH",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")
        return bill

    def test_close_paid_bills_closes_only_paid(self):
        paid1 = self._paid_bill(weekday=0)
        paid2 = self._paid_bill(weekday=1)

        # Third bill: draft, not paid
        day = _next_weekday(2)
        appt3 = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(day, time(10, 0))),
            reason="Draft",
            booked_by=self.staff,
        )
        draft = Bill.objects.create(appointment=appt3, patient=self.patient)

        # Simulate the admin action
        site = AdminSite()
        admin = BillAdmin(Bill, site)

        factory = RequestFactory()
        request = factory.post("/admin/billing/bill/")
        request.user = self.admin

        # Attach message middleware
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = "session"
        request._messages = FallbackStorage(request)

        queryset = Bill.objects.filter(pk__in=[paid1.pk, paid2.pk, draft.pk])
        admin.close_paid_bills(request, queryset)

        paid1.refresh_from_db()
        paid2.refresh_from_db()
        draft.refresh_from_db()

        self.assertEqual(paid1.status, "CLOSED")
        self.assertEqual(paid2.status, "CLOSED")
        self.assertEqual(draft.status, "DRAFT")  # unchanged
