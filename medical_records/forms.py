"""Forms and formsets for the consultation flow."""

from django import forms
from django.forms import inlineformset_factory

from .models import (
    Diagnosis,
    MedicalRecord,
    Prescription,
    PrescriptionItem,
    Vitals,
)


class MedicalRecordForm(forms.ModelForm):
    """The doctor's narrative section — chief complaint through follow-up."""

    class Meta:
        model = MedicalRecord
        fields = [
            "chief_complaint",
            "history_present_illness",
            "examination_findings",
            "clinical_notes",
            "private_notes",
            "follow_up_recommendation",
        ]
        widgets = {
            "chief_complaint": forms.TextInput(
                attrs={"placeholder": "e.g., Chest pain for 2 days"}
            ),
            "history_present_illness": forms.Textarea(attrs={"rows": 4}),
            "examination_findings": forms.Textarea(attrs={"rows": 4}),
            "clinical_notes": forms.Textarea(attrs={"rows": 3}),
            "private_notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Not visible to the patient.",
                }
            ),
            "follow_up_recommendation": forms.Textarea(attrs={"rows": 2}),
        }


class VitalsForm(forms.ModelForm):
    """Vitals form — all fields optional."""

    class Meta:
        model = Vitals
        fields = [
            "bp_systolic", "bp_diastolic",
            "pulse", "respiratory_rate", "spo2",
            "temperature",
            "weight_kg", "height_cm",
        ]
        widgets = {
            "bp_systolic": forms.NumberInput(attrs={"placeholder": "120"}),
            "bp_diastolic": forms.NumberInput(attrs={"placeholder": "80"}),
            "pulse": forms.NumberInput(attrs={"placeholder": "72"}),
            "respiratory_rate": forms.NumberInput(attrs={"placeholder": "16"}),
            "spo2": forms.NumberInput(attrs={"placeholder": "98"}),
            "temperature": forms.NumberInput(attrs={"placeholder": "36.6", "step": "0.1"}),
            "weight_kg": forms.NumberInput(attrs={"placeholder": "70.0", "step": "0.01"}),
            "height_cm": forms.NumberInput(attrs={"placeholder": "175.0", "step": "0.1"}),
        }


class DiagnosisRowForm(forms.ModelForm):
    """One diagnosis row inside the diagnosis formset."""

    class Meta:
        model = Diagnosis
        fields = ["condition", "is_primary", "notes"]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Optional detail"}),
        }


class PrescriptionForm(forms.ModelForm):
    """Prescription header (validity, general instructions, follow-up)."""

    class Meta:
        model = Prescription
        fields = ["valid_until", "general_instructions", "follow_up_after_days"]
        widgets = {
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "general_instructions": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Take with food, complete full course, etc."},
            ),
            "follow_up_after_days": forms.NumberInput(attrs={"placeholder": "e.g., 7"}),
        }


class PrescriptionItemRowForm(forms.ModelForm):
    """One prescription item row."""

    class Meta:
        model = PrescriptionItem
        fields = ["medication", "dose", "frequency", "duration_days", "instructions", "order"]
        widgets = {
            "dose": forms.TextInput(attrs={"placeholder": "1 tablet"}),
            "instructions": forms.TextInput(attrs={"placeholder": "After meals"}),
            "duration_days": forms.NumberInput(attrs={"placeholder": "5"}),
            "order": forms.HiddenInput(),
        }


# ---------- Formsets ----------

DiagnosisFormSet = inlineformset_factory(
    parent_model=MedicalRecord,
    model=Diagnosis,
    form=DiagnosisRowForm,
    extra=1,
    can_delete=True,
)


PrescriptionItemFormSet = inlineformset_factory(
    parent_model=Prescription,
    model=PrescriptionItem,
    form=PrescriptionItemRowForm,
    extra=1,
    can_delete=True,
)