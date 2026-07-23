"""Forms for the appointments app."""

from datetime import datetime

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms
from django.utils import timezone

from doctors.models import Doctor
from patients.models import Patient

from .models import Appointment


class AppointmentForm(forms.ModelForm):
    """
    Booking form. Time is a separate ChoiceField populated by JS.
    The final `scheduled_start` is composed from date + time on clean().
    """

    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Select the appointment date.",
    )
    appointment_time = forms.ChoiceField(
        choices=[("", "Select a doctor and date first")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Appointment
        fields = ["patient", "doctor", "reason", "notes"]
        widgets = {
            "reason": forms.TextInput(attrs={"placeholder": "e.g. Chest pain follow-up"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict doctor and patient dropdowns to active ones
        self.fields["doctor"].queryset = Doctor.objects.available().select_related(
            "user", "department"
        )
        self.fields["patient"].queryset = Patient.objects.active().order_by(
            "last_name", "first_name"
        )
        self.fields["notes"].required = False

        # Accept any time in POST — we validate in clean_appointment_time
        self.fields["appointment_time"].choices = (
            [(self.data.get("appointment_time", ""), "Selected")]
            if self.data.get("appointment_time")
            else [("", "Select a doctor and date first")]
        )

        # Crispy layout
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            HTML(
                '<h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-person me-2"></i>Who & What</h5>'
            ),
            "patient",
            "doctor",
            "reason",
            HTML(
                '<hr><h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-calendar me-2"></i>When</h5>'
            ),
            Row(
                Column("appointment_date", css_class="col-md-6"),
                Column("appointment_time", css_class="col-md-6"),
            ),
            HTML(
                '<hr><h5 class="text-primary mt-2 mb-3">'
                '<i class="bi bi-journal-text me-2"></i>Notes</h5>'
            ),
            "notes",
        )

    # ---------- Cleaning ----------

    def clean_appointment_date(self):
        d = self.cleaned_data["appointment_date"]
        if d < timezone.localdate():
            raise forms.ValidationError("Cannot book an appointment in the past.")
        return d

    def clean_appointment_time(self):
        t = self.cleaned_data.get("appointment_time", "")
        if not t:
            raise forms.ValidationError("Please select a time slot.")
        try:
            return datetime.strptime(t, "%H:%M").time()
        except ValueError as err:
            raise forms.ValidationError("Invalid time format.") from err

    def clean(self):
        cleaned = super().clean()
        appt_date = cleaned.get("appointment_date")
        appt_time = cleaned.get("appointment_time")

        if appt_date and appt_time:
            naive = datetime.combine(appt_date, appt_time)
            cleaned["scheduled_start"] = timezone.make_aware(naive)
            # Assign to instance for the model's clean() to validate
            self.instance.scheduled_start = cleaned["scheduled_start"]

        return cleaned

    def _post_clean(self):
        """
        Called by Django after clean() — this is where the model's clean() runs.
        We ensure scheduled_start is on the instance before that happens.
        """
        super()._post_clean()
