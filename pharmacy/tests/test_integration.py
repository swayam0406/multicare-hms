"""Cross-app integration tests: lab + pharmacy + billing."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Bill, BillItem, ServiceCatalog
from doctors.models import Department, Doctor, DoctorAvailability
from laboratory.models import LabOrder, LabOrderItem
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


class VisitLifecycleIntegrationTests(TestCase):
    """Full patient journey with lab tests and pharmacy dispenses billing correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Card", code="CARD")
        cls.doc_user = User.objects.create_user(
            username="int_doc",
            email="id@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.doctor = Doctor.objects.create(
            user=cls.doc_user,
            department=cls.dept,
            license_number="INT-1",
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
            username="int_staff",
            email="is@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
        )
        cls.pharm = User.objects.create_user(
            username="int_ph",
            email="ip@t.local",
            password="pass1234",
            role="PHARMACIST",
        )
        cls.tech = User.objects.create_user(
            username="int_tech",
            email="it@t.local",
            password="pass1234",
            role="LAB_TECH",
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
            reason="Fever",
            booked_by=cls.staff,
        )
        cls.mr = MedicalRecord.objects.create(appointment=cls.appt)

        # Consultation service + bill setup
        cls.cons_svc = ServiceCatalog.objects.create(
            code="CONS-GEN",
            name="Consultation",
            category="CONSULTATION",
            default_price=Decimal("500.00"),
        )
        cls.cbc_svc = ServiceCatalog.objects.create(
            code="LAB-CBC",
            name="CBC",
            category="LABORATORY",
            default_price=Decimal("350.00"),
        )

        # Medication + inventory
        cls.med = MedicationCatalog.objects.create(
            name="Paracetamol",
            strength="500mg",
            form="TABLET",
        )
        cls.inv = InventoryItem.objects.create(
            medication=cls.med,
            quantity_on_hand=100,
            reorder_threshold=20,
            unit_cost=Decimal("2.00"),
            unit_sale_price=Decimal("5.00"),
        )

        # Prescription for the visit
        cls.rx = Prescription.objects.create(medical_record=cls.mr)
        cls.rx_item = PrescriptionItem.objects.create(
            prescription=cls.rx,
            medication=cls.med,
            dose="1 tablet",
            frequency="TID",
            duration_days=5,
        )

    def _bill_for_visit(self):
        bill = Bill.objects.create(appointment=self.appt, patient=self.patient)
        BillItem.objects.create(bill=bill, service=self.cons_svc, quantity=1)
        bill.refresh_from_db()
        return bill

    # -------- The full journey --------

    def test_full_visit_journey_bills_all_charges(self):
        """
        Journey:
          1. Bill starts with consultation ₹500.
          2. Doctor orders a CBC lab test.
          3. Lab completes → CBC ₹350 auto-billed.
          4. Pharmacy dispenses 15 tablets @ ₹5 = ₹75 → auto-billed.
          5. Final bill total = ₹500 + ₹350 + ₹75 = ₹925.
          6. Inventory drawn down from 100 to 85.
        """
        bill = self._bill_for_visit()
        self.assertEqual(bill.total, Decimal("500.00"))

        # Step 2 + 3: Lab
        order = LabOrder.objects.create(
            medical_record=self.mr,
            patient=self.patient,
        )
        LabOrderItem.objects.create(
            order=order,
            service=self.cbc_svc,
            result_value="Normal",
        )
        order.status = "COMPLETED"
        order.save()

        bill.refresh_from_db()
        self.assertEqual(bill.total, Decimal("850.00"))

        # Step 4: Pharmacy dispense
        d = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=15,
        )
        d.mark_dispensed(user=self.pharm)

        # Final totals
        bill.refresh_from_db()
        self.assertEqual(bill.total, Decimal("925.00"))

        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 85)

    def test_multiple_dispenses_stack_on_bill(self):
        """Partial fills — two dispenses → two line items."""
        bill = self._bill_for_visit()

        d1 = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        DispenseItem.objects.create(
            dispense=d1,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=10,
        )
        d1.mark_dispensed(user=self.pharm)

        d2 = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        DispenseItem.objects.create(
            dispense=d2,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=5,
        )
        d2.mark_dispensed(user=self.pharm)

        bill.refresh_from_db()
        # Consultation (500) + 10 tablets (50) + 5 tablets (25) = 575
        self.assertEqual(bill.total, Decimal("575.00"))

        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 85)

    def test_cancelled_dispense_does_not_bill_or_drawdown(self):
        bill = self._bill_for_visit()
        starting_items = bill.items.count()

        d = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=10,
        )
        d.mark_cancelled(reason="Patient walked out", user=self.pharm)

        bill.refresh_from_db()
        self.assertEqual(bill.items.count(), starting_items)
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 100)

    def test_cancelled_lab_does_not_bill(self):
        bill = self._bill_for_visit()
        starting_items = bill.items.count()

        order = LabOrder.objects.create(
            medical_record=self.mr,
            patient=self.patient,
        )
        LabOrderItem.objects.create(order=order, service=self.cbc_svc)
        order.status = "CANCELLED"
        order.cancelled_reason = "Sample hemolyzed"
        order.save()

        bill.refresh_from_db()
        self.assertEqual(bill.items.count(), starting_items)

    def test_bill_and_pay_after_lab_and_dispense(self):
        """
        End-to-end: lab + dispense inflate bill, then patient pays in full.
        Verifies the whole chain of signals settles the bill correctly.
        """
        from billing.models import Payment

        bill = self._bill_for_visit()

        # Lab
        order = LabOrder.objects.create(
            medical_record=self.mr,
            patient=self.patient,
        )
        LabOrderItem.objects.create(
            order=order,
            service=self.cbc_svc,
            result_value="Normal",
        )
        order.status = "COMPLETED"
        order.save()

        # Dispense
        d = Dispense.objects.create(prescription=self.rx, patient=self.patient)
        DispenseItem.objects.create(
            dispense=d,
            prescription_item=self.rx_item,
            inventory_item=self.inv,
            quantity_dispensed=10,
        )
        d.mark_dispensed(user=self.pharm)

        # Finalize bill
        bill.refresh_from_db()
        bill.finalize()
        self.assertEqual(bill.status, "FINALIZED")

        # Total: 500 + 350 + 50 = 900
        self.assertEqual(bill.total, Decimal("900.00"))

        # Patient pays in full
        Payment.objects.create(
            bill=bill,
            amount=Decimal("900.00"),
            method="CASH",
            received_by=self.staff,
        )
        bill.refresh_from_db()
        self.assertEqual(bill.status, "PAID")
        self.assertEqual(bill.balance, Decimal("0.00"))


class InventoryStateInvariantsTests(TestCase):
    """Verify inventory state invariants across concurrent-ish paths."""

    @classmethod
    def setUpTestData(cls):
        cls.med = MedicationCatalog.objects.create(
            name="Paracetamol",
            strength="500mg",
            form="TABLET",
        )
        cls.inv = InventoryItem.objects.create(
            medication=cls.med,
            quantity_on_hand=50,
            reorder_threshold=20,
        )

    def test_balance_after_matches_running_total(self):
        """Each movement's balance_after equals cumulative net changes."""
        # Sequence of 5 movements
        self.inv.apply_movement("RECEIVE", 30)  # 80
        self.inv.apply_movement("DISPENSE", -10)  # 70
        self.inv.apply_movement("ADJUST", -5)  # 65
        self.inv.apply_movement("RECEIVE", 20)  # 85
        self.inv.apply_movement("DISPENSE", -25)  # 60

        movements = list(self.inv.movements.order_by("performed_at"))
        expected = [80, 70, 65, 85, 60]
        actual = [m.balance_after for m in movements]
        self.assertEqual(actual, expected)

        self.inv.refresh_from_db()
        self.assertEqual(self.inv.quantity_on_hand, 60)

    def test_low_stock_flag_reflects_after_movement(self):
        # Start at 50, threshold 20
        self.assertFalse(self.inv.is_low_stock)

        # Drop to threshold exactly
        self.inv.apply_movement("DISPENSE", -30)
        self.inv.refresh_from_db()
        self.assertTrue(self.inv.is_low_stock)  # 20 == threshold

        # Below threshold
        self.inv.apply_movement("DISPENSE", -5)
        self.inv.refresh_from_db()
        self.assertTrue(self.inv.is_low_stock)  # 15

        # Refill above threshold
        self.inv.apply_movement("RECEIVE", 10)
        self.inv.refresh_from_db()
        self.assertFalse(self.inv.is_low_stock)  # 25
