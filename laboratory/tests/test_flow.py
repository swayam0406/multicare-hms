"""Tests for lab order creation + queue + result entry flow."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from laboratory.models import LabOrder, LabOrderItem, LabTestProfile
from medical_records.models import MedicalRecord
from patients.models import Patient

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class LabFlowSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="lf_doc", email="lfd@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user, department=cls.dept,
            license_number="LF-1", specialty="x",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor, weekday=0,
            start_time=time(9, 0), end_time=time(12, 0),
        )
        cls.staff = User.objects.create_user(
            username="lf_staff", email="lfs@t.local",
            password="pass1234", role=User.Role.RECEPTIONIST,
        )
        cls.admin = User.objects.create_user(
            username="lf_admin", email="lfa@t.local",
            password="pass1234", role=User.Role.ADMIN,
        )
        cls.tech = User.objects.create_user(
            username="lf_tech", email="lft@t.local",
            password="pass1234", role="LAB_TECH",
        )
        cls.pat = User.objects.create_user(
            username="lf_pat", email="lfp@t.local",
            password="pass1234", role=User.Role.PATIENT,
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
            status="IN_PROGRESS",
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)

        cls.cbc_svc = ServiceCatalog.objects.create(
            code="LAB-CBC", name="CBC",
            category="LABORATORY", default_price=Decimal("350.00"),
        )
        cls.dengue_svc = ServiceCatalog.objects.create(
            code="LAB-DENGUE", name="Dengue NS1",
            category="LABORATORY", default_price=Decimal("900.00"),
        )
        LabTestProfile.objects.create(
            service=cls.cbc_svc, sample_type="BLOOD", unit="cells/µL",
        )


class LabOrderCreateTests(LabFlowSetup):
    def _url(self):
        return reverse("laboratory:order_create", kwargs={"appointment_pk": self.appt.pk})

    def test_doctor_can_create_order(self):
        self.client.login(username="lf_doc", password="pass1234")
        response = self.client.post(self._url(), {
            "services": [self.cbc_svc.pk, self.dengue_svc.pk],
            "clinical_notes": "Rule out dengue",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LabOrder.objects.count(), 1)
        order = LabOrder.objects.first()
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.clinical_notes, "Rule out dengue")

    def test_admin_can_create_order(self):
        self.client.login(username="lf_admin", password="pass1234")
        response = self.client.post(self._url(), {
            "services": [self.cbc_svc.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LabOrder.objects.count(), 1)

    def test_other_doctor_forbidden(self):
        other_doc_user = User.objects.create_user(
            username="lf_other", email="lfo@t.local",
            password="pass1234", role=User.Role.DOCTOR,
        )
        Doctor.objects.create(
            user=other_doc_user, department=self.dept,
            license_number="LF-2", specialty="y",
            qualifications="MBBS", consultation_fee=Decimal("500.00"),
        )
        self.client.login(username="lf_other", password="pass1234")
        response = self.client.post(self._url(), {"services": [self.cbc_svc.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(LabOrder.objects.count(), 0)

    def test_patient_forbidden(self):
        self.client.login(username="lf_pat", password="pass1234")
        response = self.client.post(self._url(), {"services": [self.cbc_svc.pk]})
        self.assertEqual(response.status_code, 403)

    def test_requires_at_least_one_service(self):
        self.client.login(username="lf_doc", password="pass1234")
        self.client.post(self._url(), {"clinical_notes": "empty"})
        self.assertEqual(LabOrder.objects.count(), 0)

    def test_rejects_non_lab_service(self):
        cons = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )
        self.client.login(username="lf_doc", password="pass1234")
        self.client.post(self._url(), {"services": [cons.pk]})
        self.assertEqual(LabOrder.objects.count(), 0)

    def test_rejects_when_appointment_not_in_progress(self):
        self.appt.status = "CONFIRMED"
        self.appt.save()
        self.client.login(username="lf_doc", password="pass1234")
        self.client.post(self._url(), {"services": [self.cbc_svc.pk]})
        self.assertEqual(LabOrder.objects.count(), 0)


class QueueAccessTests(LabFlowSetup):
    def _url(self):
        return reverse("laboratory:queue")

    def test_lab_tech_can_access(self):
        self.client.login(username="lf_tech", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access(self):
        self.client.login(username="lf_admin", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_doctor_forbidden(self):
        self.client.login(username="lf_doc", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_patient_forbidden(self):
        self.client.login(username="lf_pat", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_queue_excludes_terminal_orders(self):
        active = LabOrder.objects.create(
            medical_record=self.mr, patient=self.patient,
        )
        LabOrder.objects.create(
            medical_record=self.mr, patient=self.patient,
            status="COMPLETED",
        )
        LabOrder.objects.create(
            medical_record=self.mr, patient=self.patient,
            status="CANCELLED",
        )
        self.client.login(username="lf_tech", password="pass1234")
        response = self.client.get(self._url())
        orders = response.context["orders"]
        self.assertEqual(list(orders), [active])


class ResultEntryTests(LabFlowSetup):
    def setUp(self):
        self.order = LabOrder.objects.create(
            medical_record=self.mr, patient=self.patient,
        )
        self.cbc_item = LabOrderItem.objects.create(
            order=self.order, service=self.cbc_svc,
        )
        self.dengue_item = LabOrderItem.objects.create(
            order=self.order, service=self.dengue_svc,
        )

    def _url(self):
        return reverse("laboratory:result_entry", kwargs={"pk": self.order.pk})

    def test_tech_saves_results(self):
        self.client.login(username="lf_tech", password="pass1234")
        response = self.client.post(self._url(), {
            f"item-{self.cbc_item.pk}-result_value": "5.4",
            f"item-{self.cbc_item.pk}-is_abnormal": "on",
            f"item-{self.dengue_item.pk}-result_value": "Negative",
        })
        self.assertEqual(response.status_code, 302)
        self.cbc_item.refresh_from_db()
        self.dengue_item.refresh_from_db()
        self.assertEqual(self.cbc_item.result_value, "5.4")
        self.assertTrue(self.cbc_item.is_abnormal)
        self.assertEqual(self.dengue_item.result_value, "Negative")

    def test_result_entry_auto_advances_to_in_progress(self):
        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {
            f"item-{self.cbc_item.pk}-result_value": "5.4",
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "IN_PROGRESS")

    def test_result_entry_records_resulted_by(self):
        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {
            f"item-{self.cbc_item.pk}-result_value": "5.4",
        })
        self.cbc_item.refresh_from_db()
        self.assertEqual(self.cbc_item.resulted_by, self.tech)
        self.assertIsNotNone(self.cbc_item.resulted_at)

    def test_terminal_order_rejects_entry(self):
        self.order.status = "COMPLETED"
        self.order.save()
        self.client.login(username="lf_tech", password="pass1234")
        response = self.client.post(self._url(), {
            f"item-{self.cbc_item.pk}-result_value": "changed",
        })
        self.assertEqual(response.status_code, 302)
        self.cbc_item.refresh_from_db()
        self.assertEqual(self.cbc_item.result_value, "")


class TransitionTests(LabFlowSetup):
    def setUp(self):
        # Create a bill so the auto-billing signal has somewhere to append.
        self.bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        cons_svc = ServiceCatalog.objects.create(
            code="CONS-GEN", name="Consultation",
            category="CONSULTATION", default_price=Decimal("500.00"),
        )
        BillItem.objects.create(bill=self.bill, service=cons_svc, quantity=1)
        self.bill.refresh_from_db()
        self.bill.finalize()

        self.order = LabOrder.objects.create(
            medical_record=self.mr, patient=self.patient,
        )
        self.item = LabOrderItem.objects.create(
            order=self.order, service=self.cbc_svc,
            result_value="5.4",  # has a result — completion allowed
        )

    def _url(self):
        return reverse("laboratory:order_transition", kwargs={"pk": self.order.pk})

    def test_sample_collected_stamps_timestamp(self):
        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {"new_status": "SAMPLE_COLLECTED"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "SAMPLE_COLLECTED")
        self.assertIsNotNone(self.order.sample_collected_at)

    def test_completion_appends_to_bill(self):
        self.order.status = "IN_PROGRESS"
        self.order.save()

        starting_items = self.bill.items.count()
        starting_total = self.bill.total

        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {"new_status": "COMPLETED"})

        self.bill.refresh_from_db()
        self.assertEqual(self.bill.items.count(), starting_items + 1)
        self.assertEqual(self.bill.total, starting_total + Decimal("350.00"))

    def test_completion_requires_at_least_one_result(self):
        self.item.result_value = ""
        self.item.save()

        self.order.status = "IN_PROGRESS"
        self.order.save()

        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {"new_status": "COMPLETED"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "IN_PROGRESS")

    def test_cancel_requires_reason(self):
        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {"new_status": "CANCELLED"})
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "CANCELLED")

    def test_cancel_with_reason(self):
        self.client.login(username="lf_tech", password="pass1234")
        self.client.post(self._url(), {
            "new_status": "CANCELLED",
            "cancelled_reason": "Sample hemolyzed",
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "CANCELLED")
        self.assertEqual(self.order.cancelled_reason, "Sample hemolyzed")
        self.assertIsNotNone(self.order.cancelled_at)