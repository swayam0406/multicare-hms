"""Models for the medical_records app."""

from django.conf import settings
from django.db import models


class ConditionCatalog(models.Model):
    """ICD-10-lite diagnosis code catalog."""

    class Category(models.TextChoices):
        RESPIRATORY = "RESPIRATORY", "Respiratory"
        CARDIOVASCULAR = "CARDIOVASCULAR", "Cardiovascular"
        DIGESTIVE = "DIGESTIVE", "Digestive"
        ENDOCRINE = "ENDOCRINE", "Endocrine"
        MUSCULOSKELETAL = "MUSCULOSKELETAL", "Musculoskeletal"
        INFECTIOUS = "INFECTIOUS", "Infectious"
        MENTAL = "MENTAL", "Mental Health"
        NEUROLOGICAL = "NEUROLOGICAL", "Neurological"
        DERMATOLOGICAL = "DERMATOLOGICAL", "Dermatological"
        OTHER = "OTHER", "Other"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medical_records_condition_catalog"
        verbose_name = "Condition (catalog)"
        verbose_name_plural = "Conditions (catalog)"
        ordering = ["code"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper().strip()
        super().save(*args, **kwargs)


class MedicationCatalog(models.Model):
    """Curated medication catalog."""

    class Form(models.TextChoices):
        TABLET = "TABLET", "Tablet"
        CAPSULE = "CAPSULE", "Capsule"
        SYRUP = "SYRUP", "Syrup"
        INJECTION = "INJECTION", "Injection"
        OINTMENT = "OINTMENT", "Ointment"
        DROPS = "DROPS", "Drops"
        INHALER = "INHALER", "Inhaler"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=100)
    strength = models.CharField(max_length=50)
    form = models.CharField(max_length=20, choices=Form.choices, default=Form.TABLET)
    manufacturer = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medical_records_medication_catalog"
        verbose_name = "Medication (catalog)"
        verbose_name_plural = "Medications (catalog)"
        ordering = ["name", "strength"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "strength", "form"],
                name="unique_medication_name_strength_form",
            ),
        ]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} {self.strength} ({self.get_form_display()})"


class MedicalRecord(models.Model):
    """
    Clinical record for one appointment.
    Contains the doctor's narrative (chief complaint, HPI, examination,
    notes) plus follow-up recommendation.
    Vitals, diagnoses, and prescription attach via reverse relations.
    """

    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.PROTECT,
        related_name="medical_record",
    )

    # ---------- Narrative (patient-visible) ----------
    chief_complaint = models.CharField(
        max_length=300,
        blank=True,
        help_text="One-line summary of why the patient came.",
    )
    history_present_illness = models.TextField(
        blank=True,
        help_text="Narrative — onset, symptoms, progression, aggravating/relieving factors.",
    )
    examination_findings = models.TextField(
        blank=True,
        help_text="Clinical examination observations.",
    )
    clinical_notes = models.TextField(
        blank=True,
        help_text="Additional clinical notes (visible to patient).",
    )
    follow_up_recommendation = models.TextField(
        blank=True,
        help_text="e.g., 'Return in 2 weeks if symptoms persist.'",
    )

    # ---------- Doctor-only ----------
    private_notes = models.TextField(
        blank=True,
        help_text="Doctor-only notes. NEVER shown to the patient.",
    )

    # ---------- Locking / audit ----------
    is_locked = models.BooleanField(
        default=False,
        help_text="True once the appointment is completed. Prevents further edits via forms.",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_medical_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medical_records_medical_record"
        verbose_name = "Medical Record"
        verbose_name_plural = "Medical Records"
        ordering = ["-created_at"]

    def __str__(self):
        return f"MedicalRecord for Appointment #{self.appointment_id}"

    # ---------- Behavior ----------

    def lock(self, save: bool = True):
        """Mark the record as locked (called when appointment is completed)."""
        from django.utils import timezone

        self.is_locked = True
        self.locked_at = timezone.now()
        if save:
            self.save(update_fields=["is_locked", "locked_at", "updated_at"])

    # ---------- Convenience helpers ----------

    @property
    def patient(self):
        return self.appointment.patient

    @property
    def doctor(self):
        return self.appointment.doctor

    @property
    def has_vitals(self) -> bool:
        return hasattr(self, "vitals")

    @property
    def has_diagnoses(self) -> bool:
        return self.diagnoses.exists()

    @property
    def has_prescription(self) -> bool:
        return hasattr(self, "prescription")

    @property
    def primary_diagnosis(self):
        return self.diagnoses.filter(is_primary=True).first()


class Vitals(models.Model):
    """
    Vital signs recorded during a visit.
    Typically captured by a nurse at check-in.
    All measurements are optional.
    """

    medical_record = models.OneToOneField(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name="vitals",
    )

    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_vitals",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medical_records_vitals"
        verbose_name = "Vitals"
        verbose_name_plural = "Vitals"

    def __str__(self):
        return f"Vitals for {self.medical_record}"

    @property
    def bp(self) -> str | None:
        if self.bp_systolic and self.bp_diastolic:
            return f"{self.bp_systolic}/{self.bp_diastolic}"
        return None

    @property
    def bmi(self) -> float | None:
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            height_m = float(self.height_cm) / 100
            return round(float(self.weight_kg) / (height_m**2), 1)
        return None

    @property
    def bmi_category(self) -> str | None:
        bmi = self.bmi
        if bmi is None:
            return None
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25:
            return "Normal"
        if bmi < 30:
            return "Overweight"
        return "Obese"


class Diagnosis(models.Model):
    """
    A single diagnosis attached to a medical record.
    A visit can have multiple diagnoses; at most one is marked primary.
    """

    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )
    condition = models.ForeignKey(
        ConditionCatalog,
        on_delete=models.PROTECT,
        related_name="diagnoses",
        limit_choices_to={"is_active": True},
    )
    notes = models.TextField(
        blank=True,
        help_text="Free-form clinical detail beyond the coded condition.",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Marks this as the visit's primary diagnosis.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medical_records_diagnosis"
        verbose_name = "Diagnosis"
        verbose_name_plural = "Diagnoses"
        ordering = ["-is_primary", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["medical_record", "condition"],
                name="unique_diagnosis_per_record",
            ),
            models.UniqueConstraint(
                fields=["medical_record"],
                condition=models.Q(is_primary=True),
                name="one_primary_diagnosis_per_record",
            ),
        ]
        indexes = [
            models.Index(fields=["medical_record"]),
            models.Index(fields=["condition"]),
        ]

    def __str__(self):
        primary = " [PRIMARY]" if self.is_primary else ""
        return f"{self.condition.code} — {self.condition.name}{primary}"


class Prescription(models.Model):
    """
    A prescription document for one medical record.
    Contains N PrescriptionItem lines.
    """

    medical_record = models.OneToOneField(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name="prescription",
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="Date after which the prescription is no longer valid.",
    )
    general_instructions = models.TextField(
        blank=True,
        help_text="Applies to the whole prescription (e.g., 'Take with food').",
    )
    follow_up_after_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Recommended follow-up window in days.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medical_records_prescription"
        verbose_name = "Prescription"
        verbose_name_plural = "Prescriptions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Prescription for {self.medical_record}"

    @property
    def item_count(self) -> int:
        return self.items.count()


class PrescriptionItem(models.Model):
    """A single medication line on a prescription."""

    class Frequency(models.TextChoices):
        OD = "OD", "Once daily"
        BID = "BID", "Twice daily"
        TID = "TID", "Three times daily"
        QID = "QID", "Four times daily"
        Q4H = "Q4H", "Every 4 hours"
        Q6H = "Q6H", "Every 6 hours"
        Q8H = "Q8H", "Every 8 hours"
        HS = "HS", "At bedtime"
        PRN = "PRN", "As needed"
        STAT = "STAT", "Immediately (single dose)"

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    medication = models.ForeignKey(
        MedicationCatalog,
        on_delete=models.PROTECT,
        related_name="prescription_items",
        limit_choices_to={"is_active": True},
    )
    dose = models.CharField(
        max_length=50,
        help_text="e.g., '1 tablet', '10 ml', '2 puffs'.",
    )
    frequency = models.CharField(
        max_length=10,
        choices=Frequency.choices,
        default=Frequency.BID,
    )
    duration_days = models.PositiveSmallIntegerField(
        default=5,
        help_text="Number of days to continue this medication.",
    )
    instructions = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., 'After meals', 'With warm water'.",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order on the prescription.",
    )

    class Meta:
        db_table = "medical_records_prescription_item"
        verbose_name = "Prescription item"
        verbose_name_plural = "Prescription items"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["prescription", "medication"],
                name="unique_medication_per_prescription",
            ),
            models.CheckConstraint(
                condition=models.Q(duration_days__gte=1),
                name="prescription_item_duration_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["prescription"]),
        ]

    def __str__(self):
        return (
            f"{self.medication.name} {self.medication.strength} — "
            f"{self.dose}, {self.get_frequency_display()}, {self.duration_days}d"
        )
