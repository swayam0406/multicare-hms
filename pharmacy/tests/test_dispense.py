"""Tests for Dispense, DispenseItem, inventory drawdown, and auto-billing."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from medical_records.models import (
    MedicalRecord,
    MedicationCatalog,
    Prescription,
    PrescriptionItem,
)
from patients.models import Patient
from pharmacy.models import Dispense, DispenseItem, InventoryItem

User = get_user_model()


def _next_weekday(weekday: int):
    today = timezone.localdate()
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


class DispenseSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="disp_doc",
            email="dd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="DISP-1",
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
            username="disp_staff",
            email="ds@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.pharm = User.objects.create_user(
            username="disp_ph",
            email="dp@t.local",
            password="pass1234",
            role="PHARMACIST",
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
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)
        cls.prescription = Prescription.objects.create(medical_record=cls.mr)

        cls.med_para = MedicationCatalog.objects.create(
            name="Paracetamol",
            strength="500mg",
            form="TABLET",
        )
        cls.rx_para = PrescriptionItem.objects.create(
            prescription=cls.prescription,
            medication=cls.med_para,
            dose="1 tablet",
            frequency="TID",
            duration_days=5,
        )
        cls.inv_para = InventoryItem.objects.create(
            medication=cls.med_para,
            quantity_on_hand=100,
            reorder_threshold=20,
            unit_cost=Decimal("2.00"),
            unit_sale_price=Decimal("5.00"),
        )


class DispenseNumberingTests(DispenseSetup):
    def test_dispense_number_auto_generated(self):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        self.assertTrue(d.dispense_number.startswith("DSP-"))
        self.assertIn(str(timezone.now().year), d.dispense_number)

    def test_dispense_number_sequential(self):
        d1 = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        d2 = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        seq1 = int(d1.dispense_number.split("-")[-1])
        seq2 = int(d2.dispense_number.split("-")[-1])
        self.assertEqual(seq2, seq1 + 1)


class DispenseItemTests(DispenseSetup):
    def test_item_snapshots_unit_price(self):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        item = DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_para,
            inventory_item=self.inv_para,
            quantity_dispensed=15,
        )
        self.assertEqual(item.unit_price, Decimal("5.00"))
        self.assertEqual(item.line_total, Decimal("75.00"))

    def test_line_total_recomputes_on_change(self):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        item = DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_para,
            inventory_item=self.inv_para,
            quantity_dispensed=10,
        )
        item.quantity_dispensed = 20
        item.save()
        self.assertEqual(item.line_total, Decimal("100.00"))


class InventoryDrawdownTests(DispenseSetup):
    def _dispense_with_items(self, qty=10):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_para,
            inventory_item=self.inv_para,
            quantity_dispensed=qty,
        )
        return d

    def test_dispensed_reduces_inventory(self):
        d = self._dispense_with_items(qty=15)
        d.mark_dispensed(user=self.pharm)

        self.inv_para.refresh_from_db()
        self.assertEqual(self.inv_para.quantity_on_hand, 85)

    def test_dispensed_creates_stock_movement(self):
        d = self._dispense_with_items(qty=15)
        d.mark_dispensed(user=self.pharm)

        movement = self.inv_para.movements.first()
        self.assertEqual(movement.movement_type, "DISPENSE")
        self.assertEqual(movement.quantity, -15)
        self.assertEqual(movement.balance_after, 85)
        self.assertEqual(movement.reference, d.dispense_number)

    def test_insufficient_stock_rolls_back(self):
        d = self._dispense_with_items(qty=999)  # more than 100 in stock
        with self.assertRaises(ValidationError):
            d.mark_dispensed(user=self.pharm)

        # No state change: still pending, no drawdown
        d.refresh_from_db()
        self.assertEqual(d.status, "PENDING")
        self.inv_para.refresh_from_db()
        self.assertEqual(self.inv_para.quantity_on_hand, 100)

    def test_cannot_dispense_empty(self):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        with self.assertRaises(ValidationError):
            d.mark_dispensed(user=self.pharm)

    def test_cannot_dispense_twice(self):
        d = self._dispense_with_items(qty=10)
        d.mark_dispensed(user=self.pharm)
        with self.assertRaises(ValidationError):
            d.mark_dispensed(user=self.pharm)

    def test_cancel_leaves_inventory_untouched(self):
        d = self._dispense_with_items(qty=10)
        d.mark_cancelled(reason="Patient refused", user=self.pharm)

        self.inv_para.refresh_from_db()
        self.assertEqual(self.inv_para.quantity_on_hand, 100)
        self.assertEqual(d.status, "CANCELLED")

    def test_cancel_requires_reason(self):
        d = self._dispense_with_items(qty=10)
        with self.assertRaises(ValidationError):
            d.mark_cancelled(reason="", user=self.pharm)

    def test_multiple_items_atomic(self):
        med2 = MedicationCatalog.objects.create(
            name="Amoxicillin",
            strength="500mg",
            form="CAPSULE",
        )
        rx2 = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medication=med2,
            dose="1 capsule",
            frequency="TID",
            duration_days=5,
        )
        inv2 = InventoryItem.objects.create(
            medication=med2,
            quantity_on_hand=5,
            reorder_threshold=10,
            unit_sale_price=Decimal("10.00"),
        )

        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_para,
            inventory_item=self.inv_para,
            quantity_dispensed=15,
        )
        # This one will fail — only 5 in stock, asking for 10
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=rx2,
            inventory_item=inv2,
            quantity_dispensed=10,
        )

        with self.assertRaises(ValidationError):
            d.mark_dispensed(user=self.pharm)

        # Roll back verified — first item's inventory unchanged
        self.inv_para.refresh_from_db()
        self.assertEqual(self.inv_para.quantity_on_hand, 100)
        inv2.refresh_from_db()
        self.assertEqual(inv2.quantity_on_hand, 5)


class AutoBillingSignalTests(DispenseSetup):
    def _bill(self):
        cons = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="Consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=cons, quantity=1)
        bill.refresh_from_db()
        return bill

    def _dispense_with_items(self, qty=10):
        d = Dispense.objects.create(
            prescription=self.prescription,
            patient=self.patient,
        )
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_para,
            inventory_item=self.inv_para,
            quantity_dispensed=qty,
        )
        return d

    def test_dispensed_appends_to_bill(self):
        bill = self._bill()
        starting_items = bill.items.count()
        starting_total = bill.total

        d = self._dispense_with_items(qty=15)
        d.mark_dispensed(user=self.pharm)

        bill.refresh_from_db()
        self.assertEqual(bill.items.count(), starting_items + 1)
        # 15 tablets × ₹5 = ₹75
        self.assertEqual(bill.total, starting_total + Decimal("75.00"))

    def test_billed_flag_set_on_completion(self):
        self._bill()
        d = self._dispense_with_items(qty=10)
        d.mark_dispensed(user=self.pharm)

        for item in d.items.all():
            self.assertTrue(item.is_billed)

    def test_signal_is_idempotent(self):
        bill = self._bill()
        starting_items = bill.items.count()

        d = self._dispense_with_items(qty=10)
        d.mark_dispensed(user=self.pharm)

        bill.refresh_from_db()
        self.assertEqual(bill.items.count(), starting_items + 1)

        # Re-save the dispense (though state can't change)
        Dispense.objects.filter(pk=d.pk).update(updated_at=timezone.now())
        d.refresh_from_db()
        d.save()

        bill.refresh_from_db()
        # No duplicate item added
        self.assertEqual(bill.items.count(), starting_items + 1)

    def test_no_bill_no_error(self):
        # No bill exists for this appointment
        d = self._dispense_with_items(qty=10)
        # Should not raise
        d.mark_dispensed(user=self.pharm)

        self.inv_para.refresh_from_db()
        self.assertEqual(self.inv_para.quantity_on_hand, 90)

    def test_cancelled_does_not_bill(self):
        bill = self._bill()
        starting_items = bill.items.count()

        d = self._dispense_with_items(qty=10)
        d.mark_cancelled(reason="Test", user=self.pharm)

        bill.refresh_from_db()
        self.assertEqual(bill.items.count(), starting_items)
