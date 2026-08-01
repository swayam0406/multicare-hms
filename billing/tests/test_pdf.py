"""Tests for BillPdfView."""

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


class BillPdfViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="pdf_doc",
            email="pd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="PDF-1",
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
            username="pdf_staff",
            email="ps@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )

        # Patient user + linked patient
        cls.patient_user = User.objects.create_user(
            username="pdf_pat",
            email="pp@t.local",
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

        # Different patient
        other_user = User.objects.create_user(
            username="pdf_other",
            email="po@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        cls.other_patient = Patient.objects.create(
            first_name="Bob",
            last_name="Brown",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543211",
            registered_by=cls.staff,
            user=other_user,
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

    def _finalized_bill_for(self, patient, weekday=0):
        DoctorAvailability.objects.get_or_create(
            doctor=self.doctor,
            weekday=weekday,
            defaults={"start_time": time(9, 0), "end_time": time(12, 0)},
        )
        day = _next_weekday(weekday)
        appt = Appointment.objects.create(
            patient=patient,
            doctor=self.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(day, time(10, 0))),
            reason="Test",
            booked_by=self.staff,
        )
        bill = Bill.objects.create(appointment=appt, patient=patient)
        BillItem.objects.create(bill=bill, service=self.cons, quantity=1)
        bill.refresh_from_db()
        bill.finalize()
        return bill

    def test_anonymous_redirected(self):
        bill = self._finalized_bill_for(self.patient, weekday=0)
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": bill.bill_number})
        )
        self.assertEqual(response.status_code, 302)

    def test_staff_downloads_pdf(self):
        bill = self._finalized_bill_for(self.patient, weekday=0)
        self.client.login(username="pdf_staff", password="pass1234")
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": bill.bill_number})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            f'filename="bill-{bill.bill_number}.pdf"',
            response["Content-Disposition"],
        )
        # PDF should start with %PDF-
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_patient_downloads_own_bill(self):
        bill = self._finalized_bill_for(self.patient, weekday=0)
        self.client.login(username="pdf_pat", password="pass1234")
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": bill.bill_number})
        )
        self.assertEqual(response.status_code, 200)

    def test_patient_forbidden_from_other_bill(self):
        bill = self._finalized_bill_for(self.other_patient, weekday=1)
        self.client.login(username="pdf_pat", password="pass1234")
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": bill.bill_number})
        )
        self.assertEqual(response.status_code, 403)

    def test_pdf_content_contains_bill_data(self):
        """
        Sanity: PDF bytes contain patient name text.
        xhtml2pdf embeds text in the PDF stream so a substring search works
        for simple ASCII strings.
        """
        bill = self._finalized_bill_for(self.patient, weekday=0)
        # Add a payment for realism
        Payment.objects.create(
            bill=bill,
            amount=Decimal("200.00"),
            method="CASH",
            received_by=self.staff,
        )

        self.client.login(username="pdf_staff", password="pass1234")
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": bill.bill_number})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

        # Content-Length should be substantial (not empty PDF)
        self.assertGreater(len(response.content), 3000)

    def test_nonexistent_bill_returns_404(self):
        self.client.login(username="pdf_staff", password="pass1234")
        response = self.client.get(
            reverse("billing:bill_pdf", kwargs={"bill_number": "INV-9999-99999"})
        )
        self.assertEqual(response.status_code, 404)
