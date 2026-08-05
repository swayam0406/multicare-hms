"""
Curated demo data for presentations. Idempotent — safe to re-run.

Creates:
  - 5 patients with realistic names
  - 3 appointments today (COMPLETED, IN_PROGRESS, SCHEDULED)
  - 1 completed consultation with vitals, diagnosis, prescription
  - 1 finalized bill with a partial payment
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

        User = get_user_model()
        self.stdout.write("Seeding demo data...")

        # ---------- Staff / receptionist ----------
        staff, _ = User.objects.get_or_create(
            username="reception",
            defaults={
                "email": "reception@multicare.local",
                "role": "RECEPTIONIST",
                "first_name": "Priya",
                "last_name": "Sharma",
            },
        )
        staff.role = "RECEPTIONIST"
        staff.set_password("Demo@2026")
        staff.save()

        # ---------- Doctor ----------
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

        # ---------- Patients ----------
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

        # ---------- Today's appointments ----------
        today = timezone.localdate()

        alice_appt, _ = Appointment.objects.get_or_create(
            patient=alice,
            doctor=doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(10, 0))
            ),
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
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(11, 0))
            ),
            defaults={
                "reason": "Follow-up for hypertension",
                "booked_by": staff,
                "status": "IN_PROGRESS",
            },
        )

        Appointment.objects.get_or_create(
            patient=patients[2],
            doctor=doctor,
            scheduled_start=timezone.make_aware(
                datetime.combine(today, time(14, 0))
            ),
            defaults={
                "reason": "Routine checkup",
                "booked_by": staff,
                "status": "SCHEDULED",
            },
        )

        # ---------- Alice's medical record ----------
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

        # Diagnosis (skip silently if no matching condition seeded)
        cond = ConditionCatalog.objects.filter(name__icontains="viral").first()
        if cond:
            Diagnosis.objects.get_or_create(
                medical_record=mr,
                condition=cond,
                defaults={"is_primary": True},
            )

        # Prescription
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

        # ---------- Alice's bill ----------
        try:
            bill = alice_appt.bill
        except Bill.DoesNotExist:
            bill = Bill.objects.create(
                appointment=alice_appt,
                patient=alice,
            )
            cons_svc = ServiceCatalog.objects.filter(category="CONSULTATION").first()
            if cons_svc:
                BillItem.objects.create(
                    bill=bill,
                    service=cons_svc,
                    quantity=1,
                )

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

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data seeded: {Patient.objects.count()} patients, "
                f"{Appointment.objects.count()} appointments, "
                f"{Bill.objects.count()} bills."
            )
        )
