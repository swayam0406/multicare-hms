"""Forms for the patients app."""

from datetime import date

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms

from .models import Patient


class PatientForm(forms.ModelForm):
    """ModelForm for creating and updating Patient records."""

    class Meta:
        model = Patient
        fields = [
            # Demographics
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "blood_group",
            "marital_status",
            # Contact
            "phone",
            "email",
            "address_line",
            "city",
            "state",
            "pincode",
            # Emergency contact
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relation",
            # Medical basics
            "allergies",
            "chronic_conditions",
            "current_medications",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
            ),
            "address_line": forms.Textarea(attrs={"rows": 2}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "chronic_conditions": forms.Textarea(attrs={"rows": 2}),
            "current_medications": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make truly optional fields non-required at the form level
        for name in [
            "email",
            "address_line",
            "city",
            "state",
            "pincode",
            "marital_status",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relation",
            "allergies",
            "chronic_conditions",
            "current_medications",
        ]:
            self.fields[name].required = False

        # Crispy layout
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False  # We render <form> in the template
        self.helper.disable_csrf = True  # CSRF added in the template
        self.helper.layout = Layout(
            HTML(
                '<h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-person-vcard me-2"></i>Demographics</h5>'
            ),
            Row(
                Column("first_name", css_class="col-md-6"),
                Column("last_name", css_class="col-md-6"),
            ),
            Row(
                Column("date_of_birth", css_class="col-md-4"),
                Column("gender", css_class="col-md-4"),
                Column("blood_group", css_class="col-md-4"),
            ),
            Row(
                Column("marital_status", css_class="col-md-6"),
            ),
            HTML(
                "<hr>"
                '<h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-telephone me-2"></i>Contact Information</h5>'
            ),
            Row(
                Column("phone", css_class="col-md-6"),
                Column("email", css_class="col-md-6"),
            ),
            "address_line",
            Row(
                Column("city", css_class="col-md-4"),
                Column("state", css_class="col-md-4"),
                Column("pincode", css_class="col-md-4"),
            ),
            HTML(
                "<hr>"
                '<h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-shield-plus me-2"></i>Emergency Contact</h5>'
            ),
            Row(
                Column("emergency_contact_name", css_class="col-md-5"),
                Column("emergency_contact_phone", css_class="col-md-4"),
                Column("emergency_contact_relation", css_class="col-md-3"),
            ),
            HTML(
                "<hr>"
                '<h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-clipboard-pulse me-2"></i>Medical Basics</h5>'
            ),
            "allergies",
            "chronic_conditions",
            "current_medications",
        )

    # ---------- Custom validation ----------

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob is None:
            return dob

        today = date.today()
        if dob > today:
            raise forms.ValidationError("Date of birth cannot be in the future.")

        # Sanity bound — no one is 130+ years old
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age > 130:
            raise forms.ValidationError("Date of birth is unrealistic (age > 130).")

        return dob

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip().title()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip().title()

    def clean(self):
        cleaned = super().clean()
        # If emergency name is given, phone must be too (and vice versa)
        name = cleaned.get("emergency_contact_name")
        phone = cleaned.get("emergency_contact_phone")
        if name and not phone:
            self.add_error(
                "emergency_contact_phone",
                "Please provide a phone number for the emergency contact.",
            )
        if phone and not name:
            self.add_error(
                "emergency_contact_name",
                "Please provide a name for the emergency contact.",
            )
        return cleaned
