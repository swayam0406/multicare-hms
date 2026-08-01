"""
Seed the ServiceCatalog with a curated starter set of hospital services.

Idempotent — running twice creates no duplicates.

Usage:
    python manage.py seed_services
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import ServiceCatalog

SERVICES = [
    # (code, name, category, default_price, is_taxable)
    # Consultations
    ("CONS-GEN", "General consultation", "CONSULTATION", "500.00", False),
    ("CONS-SPEC", "Specialist consultation", "CONSULTATION", "1000.00", False),
    ("CONS-FOLLOW", "Follow-up visit", "CONSULTATION", "300.00", False),
    ("CONS-EMERG", "Emergency consultation", "CONSULTATION", "1500.00", False),
    # Laboratory
    ("LAB-CBC", "Complete Blood Count (CBC)", "LABORATORY", "350.00", False),
    ("LAB-LFT", "Liver Function Test", "LABORATORY", "600.00", False),
    ("LAB-KFT", "Kidney Function Test", "LABORATORY", "600.00", False),
    ("LAB-LIPID", "Lipid Profile", "LABORATORY", "800.00", False),
    ("LAB-HBA1C", "HbA1c (Diabetes)", "LABORATORY", "500.00", False),
    ("LAB-URINE", "Urine Routine", "LABORATORY", "200.00", False),
    ("LAB-THYROID", "Thyroid Panel (TSH, T3, T4)", "LABORATORY", "900.00", False),
    ("LAB-CULTURE", "Bacterial Culture", "LABORATORY", "1200.00", False),
    # Imaging
    ("IMG-XRAY-CHEST", "X-Ray Chest", "IMAGING", "500.00", False),
    ("IMG-XRAY-LIMB", "X-Ray Limb", "IMAGING", "600.00", False),
    ("IMG-USG-ABD", "Ultrasound Abdomen", "IMAGING", "1200.00", False),
    ("IMG-CT-BRAIN", "CT Scan Brain", "IMAGING", "4500.00", False),
    ("IMG-MRI-SPINE", "MRI Spine", "IMAGING", "8500.00", False),
    ("IMG-ECG", "ECG (12-lead)", "IMAGING", "400.00", False),
    # Procedures
    ("PROC-DRESSING", "Wound Dressing", "PROCEDURE", "300.00", False),
    ("PROC-SUTURE", "Suturing (minor)", "PROCEDURE", "800.00", False),
    ("PROC-INJ", "IM/IV Injection", "PROCEDURE", "150.00", False),
    ("PROC-NEBUL", "Nebulization", "PROCEDURE", "250.00", False),
    # Room / Ward
    ("ROOM-GEN", "General Ward (per day)", "ROOM", "1500.00", False),
    ("ROOM-PRIV", "Private Room (per day)", "ROOM", "4000.00", False),
    ("ROOM-ICU", "ICU Bed (per day)", "ROOM", "8000.00", False),
    # Other
    ("OTHER-REG", "Registration Fee", "OTHER", "100.00", False),
    ("OTHER-AMB", "Ambulance Service", "OTHER", "1500.00", False),
]


class Command(BaseCommand):
    help = "Seed ServiceCatalog with curated hospital services (idempotent)."

    def handle(self, *args, **options):
        created, skipped = 0, 0
        for code, name, category, price, is_taxable in SERVICES:
            _, is_new = ServiceCatalog.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "default_price": Decimal(price),
                    "is_taxable": is_taxable,
                },
            )
            if is_new:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Services: {created} created, {skipped} already existed.")
        )
        self.stdout.write(f"Total services in catalog: {ServiceCatalog.objects.count()}")
