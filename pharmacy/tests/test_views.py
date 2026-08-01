"""Tests for pharmacy queue + dispense flow + inventory views."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from doctors.models import Department, Doctor, DoctorAvailability
from medical_records.models import (
    MedicalRecord,
    MedicationCatalog,
    Prescription,
    PrescriptionItem,
)
from patients.models import Patient
from pharmacy.models import Dispense, InventoryItem

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class PharmacyViewsSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="pv_doc",
            email="pvd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="PV-1",
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
            username="pv_st",
            email="pvs@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.pharm = User.objects.create_user(
            username="pv_ph",
            email="pvp@t.local",
            password="pass1234",
            role="PHARMACIST",
        )
        cls.pat = User.objects.create_user(
            username="pv_pat",
            email="pvpat@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
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
            status="COMPLETED",
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)
        cls.rx = Prescription.objects.create(medical_record=cls.mr)

        cls.med_para = MedicationCatalog.objects.create(
            name="Paracetamol",
            strength="500mg",
            form="TABLET",
        )
        cls.rx_item = PrescriptionItem.objects.create(
            prescription=cls.rx,
            medication=cls.med_para,
            dose="1 tablet",
            frequency="TID",
            duration_days=5,
        )
        cls.inv = InventoryItem.objects.create(
            medication=cls.med_para,
            quantity_on_hand=100,
            reorder_threshold=20,
            unit_cost=Decimal("2.00"),
            unit_sale_price=Decimal("5.00"),
        )


class QueueAccessTests(PharmacyViewsSetup):
    def test_pharmacist_can_access(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:queue"))
        self.assertEqual(response.status_code, 200)

    def test_doctor_forbidden(self):
        self.client.login(username="pv_doc", password="pass1234")
        response = self.client.get(reverse("pharmacy:queue"))
        self.assertEqual(response.status_code, 403)

    def test_patient_forbidden(self):
        self.client.login(username="pv_pat", password="pass1234")
        response = self.client.get(reverse("pharmacy:queue"))
        self.assertEqual(response.status_code, 403)

    def test_prescription_appears_in_queue(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:queue"))
        self.assertIn(self.rx, list(response.context["prescriptions"]))

    def test_dispensed_prescription_hidden(self):
        # Create a completed dispense
        d = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        from pharmacy.models import DispenseItem

        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=15,
        )
        d.mark_dispensed(user=self.pharm)

        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:queue"))
        self.assertNotIn(self.rx, list(response.context["prescriptions"]))


class DispenseCreateTests(PharmacyViewsSetup):
    def _url(self):
        return reverse("pharmacy:dispense_create", kwargs={"prescription_pk": self.rx.pk})

    def test_get_shows_form(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paracetamol")

    def test_post_creates_dispense_and_draws_stock(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.post(
            self._url(),
            {
                f"item-{self.rx_item.pk}-inventory_id": str(self.inv.pk),
                f"item-{self.rx_item.pk}-quantity": "15",
                "notes": "Take after food",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Dispense created
        d = Dispense.objects.first()
        self.assertEqual(d.status, "DISPENSED")
        self.assertEqual(d.items.count(), 1)

        # Inventory drawn
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 85)

    def test_empty_submission_rejected(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.post(self._url(), {"notes": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Dispense.objects.count(), 0)

    def test_insufficient_stock_rolls_back(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.post(
            self._url(),
            {
                f"item-{self.rx_item.pk}-inventory_id": str(self.inv.pk),
                f"item-{self.rx_item.pk}-quantity": "999",
            },
        )
        # Rendered form again with error
        self.assertEqual(response.status_code, 200)
        # No dispense created (transaction rolled back)
        self.assertEqual(Dispense.objects.count(), 0)
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)


class InventoryListTests(PharmacyViewsSetup):
    def test_list_shows_items(self):
        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:inventory_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paracetamol")

    def test_search_filter(self):
        med2 = MedicationCatalog.objects.create(
            name="Amoxicillin",
            strength="500mg",
            form="CAPSULE",
        )
        InventoryItem.objects.create(medication=med2, quantity_on_hand=50)

        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:inventory_list") + "?q=amox")
        self.assertContains(response, "Amoxicillin")
        self.assertNotContains(response, "Paracetamol")

    def test_low_stock_filter(self):
        self.inv.quantity_on_hand = 5  # below threshold
        self.inv.save()
        med2 = MedicationCatalog.objects.create(
            name="Amoxicillin",
            strength="500mg",
            form="CAPSULE",
        )
        InventoryItem.objects.create(
            medication=med2,
            quantity_on_hand=100,
            reorder_threshold=10,
        )

        self.client.login(username="pv_ph", password="pass1234")
        response = self.client.get(reverse("pharmacy:inventory_list") + "?low=1")
        self.assertContains(response, "Paracetamol")
        self.assertNotContains(response, "Amoxicillin")


class InventoryReceiveTests(PharmacyViewsSetup):
    def _url(self):
        return reverse("pharmacy:inventory_receive", kwargs={"pk": self.inv.pk})

    def test_receive_increases_stock(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(
            self._url(),
            {
                "quantity": "50",
                "reference": "PO-2026-001",
            },
        )
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 150)

    def test_zero_rejected(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(self._url(), {"quantity": "0"})
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)

    def test_negative_rejected(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(self._url(), {"quantity": "-10"})
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)


class InventoryAdjustTests(PharmacyViewsSetup):
    def _url(self):
        return reverse("pharmacy:inventory_adjust", kwargs={"pk": self.inv.pk})

    def test_positive_adjustment(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(
            self._url(),
            {
                "quantity": "10",
                "reason": "Found extra in storage",
            },
        )
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 110)

    def test_negative_adjustment(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(
            self._url(),
            {
                "quantity": "-5",
                "reason": "Damaged",
            },
        )
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 95)

    def test_reason_required(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(self._url(), {"quantity": "10", "reason": ""})
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)

    def test_zero_rejected(self):
        self.client.login(username="pv_ph", password="pass1234")
        self.client.post(
            self._url(),
            {
                "quantity": "0",
                "reason": "Just testing",
            },
        )
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)
