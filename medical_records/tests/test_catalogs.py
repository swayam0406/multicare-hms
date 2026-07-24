"""Tests for ConditionCatalog and MedicationCatalog."""

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from medical_records.models import ConditionCatalog, MedicationCatalog


class ConditionCatalogTests(TestCase):
    def test_code_uppercased_on_save(self):
        c = ConditionCatalog.objects.create(code="j00", name="Cold")
        self.assertEqual(c.code, "J00")

    def test_code_stripped_on_save(self):
        c = ConditionCatalog.objects.create(code="  J00  ", name="Cold")
        self.assertEqual(c.code, "J00")

    def test_code_unique(self):
        ConditionCatalog.objects.create(code="J00", name="Cold")
        with self.assertRaises(IntegrityError):
            ConditionCatalog.objects.create(code="J00", name="Duplicate")

    def test_str_representation(self):
        c = ConditionCatalog.objects.create(code="J00", name="Common cold")
        self.assertEqual(str(c), "J00 — Common cold")

    def test_default_active(self):
        c = ConditionCatalog.objects.create(code="X01", name="Test")
        self.assertTrue(c.is_active)


class MedicationCatalogTests(TestCase):
    def test_str_representation(self):
        m = MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="TABLET")
        self.assertEqual(str(m), "Paracetamol 500mg (Tablet)")

    def test_uniqueness_across_name_strength_form(self):
        MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="TABLET")
        with self.assertRaises(IntegrityError):
            MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="TABLET")

    def test_same_name_different_strength_allowed(self):
        MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="TABLET")
        # Different strength — should work
        MedicationCatalog.objects.create(name="Paracetamol", strength="650mg", form="TABLET")
        self.assertEqual(MedicationCatalog.objects.count(), 2)

    def test_same_name_different_form_allowed(self):
        MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="TABLET")
        MedicationCatalog.objects.create(name="Paracetamol", strength="500mg", form="SYRUP")
        self.assertEqual(MedicationCatalog.objects.count(), 2)


class SeedCommandTests(TestCase):
    def test_command_seeds_data(self):
        call_command("seed_catalogs")
        self.assertGreater(ConditionCatalog.objects.count(), 25)
        self.assertGreater(MedicationCatalog.objects.count(), 30)

    def test_command_is_idempotent(self):
        call_command("seed_catalogs")
        first_condition_count = ConditionCatalog.objects.count()
        first_med_count = MedicationCatalog.objects.count()

        call_command("seed_catalogs")
        self.assertEqual(ConditionCatalog.objects.count(), first_condition_count)
        self.assertEqual(MedicationCatalog.objects.count(), first_med_count)
