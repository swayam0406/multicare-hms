"""Tests for LabReportPdfView."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from laboratory.models import LabOrder, LabOrderItem, LabTestProfile
from medical_records.models import MedicalRecord
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class LabReportPdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")

        cls.doc_user = User.objects.create_user(
            username="lr_doc",
            email="lrd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="LR-1",
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
            username="lr_staff",
            email="lrs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="lr_admin",
            email="lra@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        cls.tech = User.objects.create_user(
            username="lr_tech",
            email="lrt@t.local",
            password="pass1234",
            role="LAB_TECH",
        )
        cls.patient_user = User.objects.create_user(
            username="lr_pat",
            email="lrp@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        cls.patient = Patient.objects.create(
            first_name="A",
            last_name="One",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543210",
            registered_by=cls.staff,
            user=cls.patient_user,
        )

        other_pat_user = User.objects.create_user(
            username="lr_pat2",
            email="lrp2@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        cls.other_patient = Patient.objects.create(
            first_name="B",
            last_name="Two",
            date_of_birth="1990-01-01",
            gender=Patient.Gender.MALE,
            phone="9876543211",
            registered_by=cls.staff,
            user=other_pat_user,
        )

        monday = _next_weekday(0)
        cls.appt = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
            scheduled_start=timezone.make_aware(datetime.combine(monday, time(10, 0))),
            reason="Test",
            booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)

        cls.cbc_svc = ServiceCatalog.objects.create(
            code="LAB-CBC",
            name="CBC",
            category="LABORATORY",
            default_price=Decimal("350.00"),
        )
        LabTestProfile.objects.create(
            service=cls.cbc_svc,
            sample_type="BLOOD",
            unit="cells/µL",
        )

        cls.order = LabOrder.objects.create(
            medical_record=cls.mr,
            patient=cls.patient,
            ordered_by=cls.doc_user,
            status="COMPLETED",
            completed_at=timezone.now(),
        )
        LabOrderItem.objects.create(
            order=cls.order,
            service=cls.cbc_svc,
            result_value="5.4",
            resulted_by=cls.tech,
        )

    def _url(self):
        return reverse("laboratory:lab_report_pdf", kwargs={"pk": self.order.pk})

    def test_anonymous_redirected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_admin_downloads(self):
        self.client.login(username="lr_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_lab_tech_downloads(self):
        self.client.login(username="lr_tech", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_owning_doctor_downloads(self):
        self.client.login(username="lr_doc", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_owning_patient_downloads(self):
        self.client.login(username="lr_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_other_patient_forbidden(self):
        self.client.login(username="lr_pat2", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_non_completed_order_forbidden(self):
        self.order.status = "IN_PROGRESS"
        self.order.save()
        self.client.login(username="lr_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_filename_uses_order_number(self):
        self.client.login(username="lr_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertIn(
            f"lab-{self.order.order_number}.pdf",
            response["Content-Disposition"],
        )
