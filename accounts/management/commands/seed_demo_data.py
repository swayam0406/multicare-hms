"""
Curated demo data for presentations. Idempotent — safe to re-run.

Creates:
  - 1 user per role (7 total, plus admin from bootstrap)
  - 5 patients with realistic names; Alice linked to a login
  - 3 appointments today (COMPLETED, IN_PROGRESS, SCHEDULED)
  - 1 completed consultation with vitals, diagnosis, prescription
  - 1 finalized bill with a partial payment
  - Pharmacy inventory for 4 medications (one low-stock)
  - 1 completed dispense for Alice
"""

from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed curated demo data for presentation."

    def handle(self, *args, **options):
        from appointments.models import Appointment
        from billing.models import Bill, BillItem, Payment, ServiceCatalog
        from doctors.models import Department, Doctor, DoctorAvailability
        from medical_records.models import (
            ConditionCatalog,
            Diagnosis,
            MedicalRecord,
            MedicationCatalog,
            Prescription,
            PrescriptionItem,
            Vitals,
        )
        from patients.models import Patient
        from pharmacy.models import Dispense, DispenseItem, InventoryItem

        User = get_user_model()
        self.stdout.write("Seeding demo data...")

        # =========================================================
        # 1. Users — one per role
        # =========================================================
        role_users = [
            ("reception", "RECEPTIONIST", "Priya", "Sharma", "reception@multicare.local"),
            ("nurse1", "NURSE", "Anita", "Nair", "nurse@multicare.local"),
            ("labtech1", "LAB_TECH", "Sanjay", "Patel", "labtech@multicare.local"),
            ("pharma1", "PHARMACIST", "Ravi", "Kumar", "pharma@multicare.local"),
        ]
        for username, role, first, last, email in role_users:
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                },
            )
            u.role = role
            u.first_name = first
            u.last_name = last
            u.email = email
            u.set_password("Demo@2026")
            u.save()

        staff = User.objects.get(username="reception")

        # =========================================================
        # 2. Doctor
        # =========================================================
        doc_user, _ = User.objects.get_or_create(
            username="dr_sharma",
            defaults={
                "email": "dr.sharma@multicare.local",
                "role": "DOCTOR",
                "first_name": "Rajesh",
                "last_name": "Sharma",
            },
        )
        doc_user.role = "DOCTOR"
        doc_user.first_name = "Rajesh"
        doc_user.last_name = "Sharma"
        doc_user.set_password("Demo@2026")
        doc_user.save()

        dept, _ = Department.objects.get_or_create(
            code="GEN",
            defaults={"name": "General Medicine"},
        )
        doctor, _ = Doctor.objects.get_or_create(
            user=doc_user,
            defaults={
                "department": dept,
                "license_number": "MC-DOC-001",
                "specialty": "General Medicine",
                "qualifications": "MBBS, MD",
                "consultation_fee": Decimal("500.00"),
            },
        )
        for weekday in range(7):
            DoctorAvailability.objects.get_or_create(
                doctor=doctor,
                weekday=weekday,
                defaults={"start_time": time(9, 0), "end_time": time(17, 0)},
            )

        # =========================================================
        # 3. Patients
        # =========================================================
        patients_data = [
            ("Alice", "Anderson", "F", "1990-04-15", "9876543210"),
            ("Bhavesh", "Bansal", "M", "1985-07-22", "9876543211"),
            ("Chandni", "Chopra", "F", "1975-11-30", "9876543212"),
            ("Dhruv", "Desai", "M", "1995-02-10", "9876543213"),
            ("Esha", "Iyer", "F", "1988-09-05", "9876543214"),
        ]
        patients = []
        for first, last, gender, dob, phone in patients_data:
            p, _ = Patient.objects.get_or_create(
                first_name=first,
                last_name=last,
                phone=phone,
                defaults={
                    "date_of_birth": dob,
                    "gender": gender,
                    "registered_by": staff,
                },
            )
            patients.append(p)

        alice = patients[0]

        # Give Alice a login
        alice_user, _ = User.objects.get_or_create(
            username="alice",
            defaults={
                "email": "alice@example.com",
                "role": "PATIENT",
                "first_name": "Alice",
                "last_name": "Anderson",
            },
        )
        alice_user.role = "PATIENT"
        alice_user.set_password("Demo@2026")
        alice_user.save()
        alice.user = alice_user
        alice.save()

        # =========================================================
        # 4. Today's appointments
        # =========================================================
        today = timezone.localdate()

        alice_appt, _ = Appointment.objects.get_or_create(
            patient=alice,
            doctor=doctor,
            scheduled_start=timezone.make_aware(datetime.combine(today, time(10, 0))),
            defaults={
                "reason": "Persistent fever and body aches",
                "booked_by": staff,
                "status": "COMPLETED",
            },
        )
        if alice_appt.status != "COMPLETED":
            alice_appt.status = "COMPLETED"
            alice_appt.save()

        Appointment.objects.get_or_create(
            patient=patients[1],
            doctor=doctor,
            scheduled_start=timezone.make_aware(datetime.combine(today, time(11, 0))),
            defaults={
                "reason": "Follow-up for hypertension",
                "booked_by": staff,
                "status": "IN_PROGRESS",
            },
        )

        Appointment.objects.get_or_create(
            patient=patients[2],
            doctor=doctor,
            scheduled_start=timezone.make_aware(datetime.combine(today, time(14, 0))),
            defaults={
                "reason": "Routine checkup",
                "booked_by": staff,
                "status": "SCHEDULED",
            },
        )

        # =========================================================
        # 5. Alice's medical record
        # =========================================================
        mr, _ = MedicalRecord.objects.get_or_create(
            appointment=alice_appt,
            defaults={
                "chief_complaint": "Fever for 3 days, generalized body aches, mild headache",
                "history_present_illness": "Started Monday evening. Low grade initially, escalated Tuesday.",
                "examination_findings": "Temperature 38.2C. Throat mildly injected. No lymphadenopathy.",
                "clinical_notes": "Likely viral upper respiratory infection.",
                "follow_up_recommendation": "Return in 5 days if not improving.",
                "created_by": doc_user,
            },
        )

        Vitals.objects.get_or_create(
            medical_record=mr,
            defaults={
                "bp_systolic": 118,
                "bp_diastolic": 76,
                "pulse": 88,
                "respiratory_rate": 16,
                "spo2": 98,
                "temperature": Decimal("38.2"),
                "weight_kg": Decimal("58.5"),
                "height_cm": Decimal("162.0"),
                "recorded_by": doc_user,
            },
        )

        cond = ConditionCatalog.objects.filter(name__icontains="viral").first()
        if cond:
            Diagnosis.objects.get_or_create(
                medical_record=mr,
                condition=cond,
                defaults={"is_primary": True},
            )

        rx, _ = Prescription.objects.get_or_create(
            medical_record=mr,
            defaults={
                "general_instructions": "Rest, plenty of fluids. Return if fever above 39C.",
                "follow_up_after_days": 5,
            },
        )
        med = MedicationCatalog.objects.filter(name__icontains="paracetamol").first()
        if med:
            PrescriptionItem.objects.get_or_create(
                prescription=rx,
                medication=med,
                defaults={
                    "dose": "1 tablet",
                    "frequency": "TID",
                    "duration_days": 5,
                    "instructions": "After meals",
                },
            )

        # =========================================================
        # 6. Alice's bill + partial payment
        # =========================================================
        try:
            bill = alice_appt.bill
        except Bill.DoesNotExist:
            bill = Bill.objects.create(appointment=alice_appt, patient=alice)
            cons_svc = ServiceCatalog.objects.filter(category="CONSULTATION").first()
            if cons_svc:
                BillItem.objects.create(bill=bill, service=cons_svc, quantity=1)

        bill.refresh_from_db()
        if bill.status == "DRAFT":
            bill.finalize()

        if bill.status in ["FINALIZED", "PARTIAL"] and bill.paid_amount == 0:
            Payment.objects.create(
                bill=bill,
                amount=Decimal("300.00"),
                method="CASH",
                received_by=staff,
            )

        # =========================================================
        # 7. Pharmacy inventory
        # =========================================================
        inventory_setup = [
            ("paracetamol", 250, 50, Decimal("2.00"), Decimal("5.00")),
            ("amoxicillin", 180, 40, Decimal("8.00"), Decimal("15.00")),
            ("ibuprofen", 30, 40, Decimal("3.00"), Decimal("7.00")),  # LOW STOCK
            ("cetirizine", 400, 50, Decimal("1.50"), Decimal("4.00")),
        ]
        for name_frag, qty, reorder, cost, sale in inventory_setup:
            m = MedicationCatalog.objects.filter(name__icontains=name_frag).first()
            if not m:
                continue
            InventoryItem.objects.update_or_create(
                medication=m,
                defaults={
                    "quantity_on_hand": qty,
                    "reorder_threshold": reorder,
                    "unit_cost": cost,
                    "unit_sale_price": sale,
                    "last_restocked_at": timezone.now(),
                },
            )

        # =========================================================
        # 8. One completed dispense for Alice
        # =========================================================
        rx_item = PrescriptionItem.objects.filter(
            prescription=rx,
            medication__name__icontains="paracetamol",
        ).first()

        if rx_item:
            paracetamol_inv = InventoryItem.objects.filter(
                medication=rx_item.medication,
            ).first()
            if paracetamol_inv and paracetamol_inv.quantity_on_hand >= 15:
                pharma_user = User.objects.get(username="pharma1")

                dispense, created = Dispense.objects.get_or_create(
                    prescription=rx,
                    defaults={
                        "patient": alice,
                        "dispensed_by": pharma_user,
                        "status": "PENDING",
                    },
                )
                if created:
                    DispenseItem.objects.create(
                        dispense=dispense,
                        prescription_item=rx_item,
                        inventory_item=paracetamol_inv,
                        quantity_dispensed=15,
                        unit_price=paracetamol_inv.unit_sale_price,
                    )
                    try:
                        dispense.status = "DISPENSED"
                        dispense.dispensed_at = timezone.now()
                        dispense.save()
                    except Exception as exc:
                        self.stdout.write(
                            self.style.WARNING(f"  Dispense state transition skipped: {exc}")
                        )

        # =========================================================
        # Done
        # =========================================================
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data seeded: {Patient.objects.count()} patients, "
                f"{Appointment.objects.count()} appointments, "
                f"{Bill.objects.count()} bills, "
                f"{User.objects.count()} users."
            )
        )
