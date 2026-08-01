"""Tests for LabTestProfile + seed command."""

from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from billing.models import ServiceCatalog
from laboratory.models import LabTestProfile


class LabTestProfileTests(TestCase):
    def test_create_profile(self):
        svc = ServiceCatalog.objects.create(
            code="LAB-TEST",
            name="Test",
            category="LABORATORY",
            default_price=Decimal("100.00"),
        )
        profile = LabTestProfile.objects.create(
            service=svc,
            sample_type="BLOOD",
            unit="mg/dL",
            reference_range="70-100",
        )
        self.assertEqual(profile.sample_type, "BLOOD")
        self.assertEqual(profile.name, "Test")
        self.assertEqual(profile.code, "LAB-TEST")

    def test_one_profile_per_service(self):
        svc = ServiceCatalog.objects.create(
            code="LAB-TEST",
            name="Test",
            category="LABORATORY",
            default_price=Decimal("100.00"),
        )
        LabTestProfile.objects.create(service=svc, sample_type="BLOOD")
        with self.assertRaises(IntegrityError):
            LabTestProfile.objects.create(service=svc, sample_type="URINE")

    def test_str_representation(self):
        svc = ServiceCatalog.objects.create(
            code="LAB-XYZ",
            name="XYZ",
            category="LABORATORY",
            default_price=Decimal("100.00"),
        )
        p = LabTestProfile.objects.create(service=svc, sample_type="URINE")
        self.assertEqual(str(p), "LAB-XYZ — Urine")

    def test_service_cascade_delete(self):
        svc = ServiceCatalog.objects.create(
            code="LAB-CASCADE",
            name="Cascade",
            category="LABORATORY",
            default_price=Decimal("100.00"),
        )
        LabTestProfile.objects.create(service=svc, sample_type="BLOOD")
        svc.delete()
        self.assertEqual(LabTestProfile.objects.count(), 0)


class SeedLabTestsCommandTests(TestCase):
    def test_command_seeds_data(self):
        # First seed the base services (from billing app)
        call_command("seed_services")
        # Then seed lab metadata
        call_command("seed_lab_tests")

        # 8 LAB services from seed_services + 12 new from seed_lab_tests = 20
        lab_services = ServiceCatalog.objects.filter(category="LABORATORY")
        self.assertGreaterEqual(lab_services.count(), 20)

        profiles = LabTestProfile.objects.all()
        self.assertGreaterEqual(profiles.count(), 20)

    def test_command_is_idempotent(self):
        call_command("seed_services")
        call_command("seed_lab_tests")
        first_lab_count = ServiceCatalog.objects.filter(category="LABORATORY").count()
        first_profile_count = LabTestProfile.objects.count()

        call_command("seed_lab_tests")
        self.assertEqual(
            ServiceCatalog.objects.filter(category="LABORATORY").count(),
            first_lab_count,
        )
        self.assertEqual(LabTestProfile.objects.count(), first_profile_count)

    def test_all_profiles_have_valid_sample_type(self):
        call_command("seed_services")
        call_command("seed_lab_tests")
        valid_types = {"BLOOD", "URINE", "STOOL", "SWAB", "OTHER"}
        for profile in LabTestProfile.objects.all():
            self.assertIn(profile.sample_type, valid_types)

    def test_lipid_profile_has_fasting_note(self):
        call_command("seed_services")
        call_command("seed_lab_tests")
        lipid = LabTestProfile.objects.get(service__code="LAB-LIPID")
        self.assertIn("Fasting", lipid.preparation_notes)
