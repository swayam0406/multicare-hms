"""
Seed lab tests: create new ServiceCatalog entries for lab services + LabTestProfile
metadata for all LAB services.

Idempotent — running twice creates no duplicates.

Usage:
    python manage.py seed_lab_tests
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import ServiceCatalog
from laboratory.models import LabTestProfile

# ---------- New lab services to add to ServiceCatalog ----------
# (code, name, default_price)
NEW_LAB_SERVICES = [
    ("LAB-BSF", "Blood sugar (fasting)", "150.00"),
    ("LAB-BSPP", "Blood sugar (post-prandial)", "150.00"),
    ("LAB-HB", "Hemoglobin", "150.00"),
    ("LAB-ESR", "Erythrocyte sedimentation rate", "200.00"),
    ("LAB-VITD", "Vitamin D (25-OH)", "1200.00"),
    ("LAB-VITB12", "Vitamin B12", "900.00"),
    ("LAB-IRON", "Serum iron", "500.00"),
    ("LAB-CRP", "C-reactive protein", "500.00"),
    ("LAB-PSA", "PSA (prostate)", "800.00"),
    ("LAB-STOOL", "Stool routine", "250.00"),
    ("LAB-COVID", "COVID-19 RT-PCR", "1500.00"),
    ("LAB-DENGUE", "Dengue NS1 antigen", "900.00"),
]


# ---------- Lab profile metadata ----------
# (service_code, sample_type, unit, reference_range, turnaround_hours, prep_notes)
PROFILES = [
    # Pre-existing services from Sprint 6
    ("LAB-CBC", "BLOOD", "cells/µL", "See report — multi-parameter", 4, ""),
    ("LAB-LFT", "BLOOD", "U/L", "See report — multi-parameter", 8, ""),
    ("LAB-KFT", "BLOOD", "mg/dL", "See report — multi-parameter", 8, ""),
    (
        "LAB-LIPID",
        "BLOOD",
        "mg/dL",
        "Cholesterol <200; LDL <100",
        8,
        "Fasting for 12 hours required.",
    ),
    ("LAB-HBA1C", "BLOOD", "%", "Normal <5.7; Diabetes ≥6.5", 12, ""),
    ("LAB-URINE", "URINE", "", "See report", 4, "Mid-stream clean-catch sample required."),
    ("LAB-THYROID", "BLOOD", "µIU/mL", "TSH: 0.4-4.0", 24, ""),
    (
        "LAB-CULTURE",
        "SWAB",
        "",
        "See report",
        48,
        "Sample collected before antibiotic administration.",
    ),
    # New services (seeded above)
    ("LAB-BSF", "BLOOD", "mg/dL", "70-100", 2, "Fasting for 8-12 hours required."),
    ("LAB-BSPP", "BLOOD", "mg/dL", "<140", 2, "Collect 2 hours after a meal."),
    ("LAB-HB", "BLOOD", "g/dL", "M: 13-17; F: 12-15", 2, ""),
    ("LAB-ESR", "BLOOD", "mm/hr", "M: <15; F: <20", 4, ""),
    ("LAB-VITD", "BLOOD", "ng/mL", "30-100 (sufficient)", 48, ""),
    ("LAB-VITB12", "BLOOD", "pg/mL", "200-900", 24, ""),
    ("LAB-IRON", "BLOOD", "µg/dL", "60-170", 24, ""),
    ("LAB-CRP", "BLOOD", "mg/L", "<10", 4, ""),
    ("LAB-PSA", "BLOOD", "ng/mL", "<4.0", 24, ""),
    ("LAB-STOOL", "STOOL", "", "See report", 4, ""),
    ("LAB-COVID", "SWAB", "", "Negative", 24, "Nasopharyngeal swab required."),
    ("LAB-DENGUE", "BLOOD", "", "Negative", 24, ""),
]


class Command(BaseCommand):
    help = "Seed new lab services + LabTestProfile metadata for all LAB services."

    def handle(self, *args, **options):
        # ---------- 1. Create new ServiceCatalog entries ----------
        svc_created, svc_skipped = 0, 0
        for code, name, price in NEW_LAB_SERVICES:
            _, is_new = ServiceCatalog.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": "LABORATORY",
                    "default_price": Decimal(price),
                },
            )
            if is_new:
                svc_created += 1
            else:
                svc_skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Lab services: {svc_created} created, {svc_skipped} already existed."
            )
        )

        # ---------- 2. Create/update LabTestProfile records ----------
        prof_created, prof_skipped = 0, 0
        prof_missing = []
        for code, sample_type, unit, ref_range, turnaround, prep in PROFILES:
            try:
                service = ServiceCatalog.objects.get(code=code)
            except ServiceCatalog.DoesNotExist:
                prof_missing.append(code)
                continue

            _, is_new = LabTestProfile.objects.get_or_create(
                service=service,
                defaults={
                    "sample_type": sample_type,
                    "unit": unit,
                    "reference_range": ref_range,
                    "turnaround_hours": turnaround,
                    "preparation_notes": prep,
                },
            )
            if is_new:
                prof_created += 1
            else:
                prof_skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Lab profiles: {prof_created} created, {prof_skipped} already existed."
            )
        )

        if prof_missing:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {len(prof_missing)} profiles (service not in catalog): "
                    f"{', '.join(prof_missing)}"
                )
            )

        total = LabTestProfile.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\nTotal lab profiles: {total}"))
