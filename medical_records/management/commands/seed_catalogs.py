"""
Seed the ConditionCatalog and MedicationCatalog with a curated starter set.

Idempotent — running twice creates no duplicates.

Usage:
    python manage.py seed_catalogs
"""

from django.core.management.base import BaseCommand

from medical_records.models import ConditionCatalog, MedicationCatalog

CONDITIONS = [
    # (code, name, category)
    # Respiratory
    ("J00", "Common cold", "RESPIRATORY"),
    ("J06.9", "Acute upper respiratory infection", "RESPIRATORY"),
    ("J20.9", "Acute bronchitis", "RESPIRATORY"),
    ("J45.9", "Asthma, unspecified", "RESPIRATORY"),
    ("J18.9", "Pneumonia, unspecified", "RESPIRATORY"),
    # Cardiovascular
    ("I10", "Essential (primary) hypertension", "CARDIOVASCULAR"),
    ("I25.10", "Chronic ischemic heart disease", "CARDIOVASCULAR"),
    ("I50.9", "Heart failure, unspecified", "CARDIOVASCULAR"),
    # Digestive
    ("K21.9", "Gastro-esophageal reflux disease (GERD)", "DIGESTIVE"),
    ("K29.7", "Gastritis, unspecified", "DIGESTIVE"),
    ("K59.0", "Constipation", "DIGESTIVE"),
    ("A09", "Infectious gastroenteritis and colitis", "DIGESTIVE"),
    # Endocrine
    ("E11.9", "Type 2 diabetes mellitus, no complications", "ENDOCRINE"),
    ("E78.5", "Hyperlipidemia, unspecified", "ENDOCRINE"),
    ("E03.9", "Hypothyroidism, unspecified", "ENDOCRINE"),
    # Musculoskeletal
    ("M54.5", "Low back pain", "MUSCULOSKELETAL"),
    ("M25.5", "Joint pain", "MUSCULOSKELETAL"),
    ("M79.3", "Muscle pain (myalgia)", "MUSCULOSKELETAL"),
    # Infectious
    ("A90", "Dengue fever", "INFECTIOUS"),
    ("B34.9", "Viral infection, unspecified", "INFECTIOUS"),
    ("N39.0", "Urinary tract infection", "INFECTIOUS"),
    # Mental
    ("F41.9", "Anxiety disorder, unspecified", "MENTAL"),
    ("F32.9", "Depressive episode, unspecified", "MENTAL"),
    ("F51.0", "Insomnia (non-organic)", "MENTAL"),
    # Neurological
    ("G43.9", "Migraine, unspecified", "NEUROLOGICAL"),
    ("R51", "Headache", "NEUROLOGICAL"),
    ("G47.9", "Sleep disorder, unspecified", "NEUROLOGICAL"),
    # Dermatological
    ("L23.9", "Allergic contact dermatitis", "DERMATOLOGICAL"),
    ("L50.9", "Urticaria (hives)", "DERMATOLOGICAL"),
    # Other
    ("R50.9", "Fever, unspecified", "OTHER"),
    ("R05", "Cough", "OTHER"),
    ("Z00.0", "General adult medical examination", "OTHER"),
]


MEDICATIONS = [
    # (name, strength, form, manufacturer)
    # Analgesics / antipyretics
    ("Paracetamol", "500mg", "TABLET", "Generic"),
    ("Paracetamol", "125mg/5ml", "SYRUP", "Generic"),
    ("Ibuprofen", "400mg", "TABLET", "Generic"),
    ("Diclofenac", "50mg", "TABLET", "Generic"),
    ("Aspirin", "75mg", "TABLET", "Generic"),
    # Antibiotics
    ("Amoxicillin", "500mg", "CAPSULE", "Generic"),
    ("Amoxicillin + Clavulanate", "625mg", "TABLET", "Generic"),
    ("Azithromycin", "500mg", "TABLET", "Generic"),
    ("Ciprofloxacin", "500mg", "TABLET", "Generic"),
    ("Doxycycline", "100mg", "CAPSULE", "Generic"),
    ("Cefixime", "200mg", "TABLET", "Generic"),
    # GI
    ("Omeprazole", "20mg", "CAPSULE", "Generic"),
    ("Pantoprazole", "40mg", "TABLET", "Generic"),
    ("Ranitidine", "150mg", "TABLET", "Generic"),
    ("Ondansetron", "4mg", "TABLET", "Generic"),
    ("Domperidone", "10mg", "TABLET", "Generic"),
    ("Loperamide", "2mg", "CAPSULE", "Generic"),
    ("ORS", "20.5g/L", "OTHER", "Generic"),
    # Respiratory / anti-allergy
    ("Cetirizine", "10mg", "TABLET", "Generic"),
    ("Levocetirizine", "5mg", "TABLET", "Generic"),
    ("Montelukast", "10mg", "TABLET", "Generic"),
    ("Salbutamol", "100mcg/dose", "INHALER", "Generic"),
    ("Dextromethorphan", "10mg/5ml", "SYRUP", "Generic"),
    # Cardiovascular
    ("Amlodipine", "5mg", "TABLET", "Generic"),
    ("Losartan", "50mg", "TABLET", "Generic"),
    ("Metoprolol", "25mg", "TABLET", "Generic"),
    ("Atorvastatin", "10mg", "TABLET", "Generic"),
    # Endocrine
    ("Metformin", "500mg", "TABLET", "Generic"),
    ("Glimepiride", "1mg", "TABLET", "Generic"),
    ("Levothyroxine", "50mcg", "TABLET", "Generic"),
    # Vitamins / supplements
    ("Vitamin D3", "60000 IU", "TABLET", "Generic"),
    ("Vitamin B12", "1500mcg", "TABLET", "Generic"),
    ("Iron (Ferrous Sulfate)", "60mg", "TABLET", "Generic"),
    ("Calcium + Vitamin D3", "500mg + 250 IU", "TABLET", "Generic"),
    # Mental / sleep
    ("Sertraline", "50mg", "TABLET", "Generic"),
    ("Alprazolam", "0.25mg", "TABLET", "Generic"),
    ("Melatonin", "3mg", "TABLET", "Generic"),
    # Topical
    ("Hydrocortisone", "1%", "OINTMENT", "Generic"),
    ("Clotrimazole", "1%", "OINTMENT", "Generic"),
    # Injectables
    ("Tetanus Toxoid", "0.5ml", "INJECTION", "Generic"),
]


class Command(BaseCommand):
    help = "Seed ConditionCatalog and MedicationCatalog with a curated starter set."

    def handle(self, *args, **options):
        # ---------- Conditions ----------
        created_c, skipped_c = 0, 0
        for code, name, category in CONDITIONS:
            _, created = ConditionCatalog.objects.get_or_create(
                code=code,
                defaults={"name": name, "category": category},
            )
            if created:
                created_c += 1
            else:
                skipped_c += 1

        # ---------- Medications ----------
        created_m, skipped_m = 0, 0
        for name, strength, form, manufacturer in MEDICATIONS:
            _, created = MedicationCatalog.objects.get_or_create(
                name=name,
                strength=strength,
                form=form,
                defaults={"manufacturer": manufacturer},
            )
            if created:
                created_m += 1
            else:
                skipped_m += 1

        self.stdout.write(
            self.style.SUCCESS(f"Conditions:   {created_c} created, {skipped_c} already existed.")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Medications:  {created_m} created, {skipped_m} already existed.")
        )
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal conditions: {ConditionCatalog.objects.count()}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Total medications: {MedicationCatalog.objects.count()}")
        )
