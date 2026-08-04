"""Tests for InventoryItem + StockMovement + apply_movement."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.template import Context, Template
from django.test import TestCase

from medical_records.models import MedicationCatalog
from pharmacy.models import InventoryItem, StockMovement

User = get_user_model()


def _make_med(name="Paracetamol", strength="500mg", form="TABLET"):
    """Create a MedicationCatalog entry using only the fields we're sure exist."""
    return MedicationCatalog.objects.create(
        name=name,
        strength=strength,
        form=form,
    )


class InventoryItemBasicsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.med = _make_med()
        cls.user = User.objects.create_user(
            username="ph",
            email="ph@t.local",
            password="pass1234",
            role="PHARMACIST",
        )

    def test_create_item(self):
        item = InventoryItem.objects.create(
            medication=self.med,
            quantity_on_hand=100,
            reorder_threshold=20,
        )
        self.assertEqual(item.quantity_on_hand, 100)
        self.assertFalse(item.is_low_stock)

    def test_low_stock_detection(self):
        item = InventoryItem.objects.create(
            medication=self.med,
            quantity_on_hand=15,
            reorder_threshold=20,
        )
        self.assertTrue(item.is_low_stock)

        item.quantity_on_hand = 20
        self.assertTrue(item.is_low_stock)  # Boundary — at threshold

        item.quantity_on_hand = 21
        self.assertFalse(item.is_low_stock)

    def test_one_inventory_per_medication(self):
        InventoryItem.objects.create(medication=self.med)
        with self.assertRaises(IntegrityError):
            InventoryItem.objects.create(medication=self.med)

    def test_str_representation(self):
        item = InventoryItem.objects.create(medication=self.med, quantity_on_hand=50)
        self.assertIn("Paracetamol", str(item))
        self.assertIn("50", str(item))


class ApplyMovementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.med = _make_med()
        cls.user = User.objects.create_user(
            username="ph",
            email="ph@t.local",
            password="pass1234",
            role="PHARMACIST",
        )

    def _fresh_item(self, qty=100):
        return InventoryItem.objects.create(
            medication=self.med,
            quantity_on_hand=qty,
            reorder_threshold=20,
        )

    def test_receive_increases_stock(self):
        item = self._fresh_item(qty=50)
        item.apply_movement("RECEIVE", 25, performed_by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 75)

    def test_receive_sets_last_restocked_at(self):
        item = self._fresh_item(qty=50)
        self.assertIsNone(item.last_restocked_at)
        item.apply_movement("RECEIVE", 25, performed_by=self.user)
        item.refresh_from_db()
        self.assertIsNotNone(item.last_restocked_at)

    def test_dispense_decreases_stock(self):
        item = self._fresh_item(qty=50)
        item.apply_movement("DISPENSE", -10, performed_by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 40)

    def test_dispense_beyond_stock_rejected(self):
        item = self._fresh_item(qty=10)
        with self.assertRaises(ValidationError):
            item.apply_movement("DISPENSE", -20, performed_by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 10)

    def test_zero_movement_rejected(self):
        item = self._fresh_item(qty=50)
        with self.assertRaises(ValidationError):
            item.apply_movement("ADJUST", 0, performed_by=self.user)

    def test_movement_creates_audit_record(self):
        item = self._fresh_item(qty=50)
        movement = item.apply_movement(
            "RECEIVE",
            25,
            performed_by=self.user,
            reference="PO-123",
        )
        self.assertEqual(movement.balance_after, 75)
        self.assertEqual(movement.quantity, 25)
        self.assertEqual(movement.reference, "PO-123")
        self.assertEqual(movement.performed_by, self.user)

    def test_multiple_movements_accumulate(self):
        item = self._fresh_item(qty=100)
        item.apply_movement("DISPENSE", -30, performed_by=self.user)
        item.apply_movement("DISPENSE", -20, performed_by=self.user)
        item.apply_movement("RECEIVE", 50, performed_by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 100)
        self.assertEqual(item.movements.count(), 3)


class StockMovementImmutabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.med = _make_med()
        cls.item = InventoryItem.objects.create(
            medication=cls.med,
            quantity_on_hand=100,
            reorder_threshold=20,
        )

    def test_cannot_delete_movement(self):
        movement = self.item.apply_movement("RECEIVE", 10)
        with self.assertRaises(ValidationError):
            movement.delete()

    def test_cannot_change_quantity(self):
        movement = self.item.apply_movement("RECEIVE", 10)
        movement.quantity = 999
        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_cannot_change_type(self):
        movement = self.item.apply_movement("RECEIVE", 10)
        movement.movement_type = "DISPENSE"
        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_db_constraint_rejects_zero(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(
                    inventory_item=self.item,
                    movement_type="ADJUST",
                    quantity=0,
                    balance_after=100,
                )


class LowStockQuerysetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        m1 = _make_med(name="Med1")
        m2 = _make_med(name="Med2")
        m3 = _make_med(name="Med3")
        cls.i1 = InventoryItem.objects.create(
            medication=m1,
            quantity_on_hand=5,
            reorder_threshold=10,
        )
        cls.i2 = InventoryItem.objects.create(
            medication=m2,
            quantity_on_hand=10,
            reorder_threshold=10,
        )
        cls.i3 = InventoryItem.objects.create(
            medication=m3,
            quantity_on_hand=100,
            reorder_threshold=10,
        )

    def test_low_stock_queryset(self):
        from pharmacy.views import low_stock_items

        items = list(low_stock_items())
        self.assertEqual(len(items), 2)
        self.assertIn(self.i1, items)
        self.assertIn(self.i2, items)
        self.assertNotIn(self.i3, items)


class LowStockTemplateTagTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _render(self):
        template = Template("{% load pharmacy_tags %}{% low_stock_count %}")
        return template.render(Context({})).strip()

    def test_zero_when_no_inventory(self):
        self.assertEqual(self._render(), "0")

    def test_counts_low_stock_only(self):
        m1 = _make_med(name="Med1")
        m2 = _make_med(name="Med2")
        InventoryItem.objects.create(
            medication=m1,
            quantity_on_hand=5,
            reorder_threshold=10,
        )
        InventoryItem.objects.create(
            medication=m2,
            quantity_on_hand=100,
            reorder_threshold=10,
        )
        self.assertEqual(self._render(), "1")
