"""Views for the medical_records app."""

"""Views for the medical_records app."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View


from .forms import (
    DiagnosisFormSet,
    MedicalRecordForm,
    PrescriptionForm,
    PrescriptionItemFormSet,
    VitalsForm,
)
from .mixins import ConsultationAccessMixin
from .models import MedicalRecord, Prescription, Vitals


class ConsultationView(ConsultationAccessMixin, View):

    """
    The doctor-facing consultation form.
    Renders one page with MedicalRecord narrative + Vitals + Diagnoses formset
    + Prescription header + PrescriptionItems formset.

    Available while the appointment is IN_PROGRESS.
    Read-only redirect otherwise.
    """

    template_name = "medical_records/consultation.html"

    def get(self, request, appointment_pk):
        return self._render(request)

    def post(self, request, appointment_pk):
        appt = self.appointment
        if appt.status != "IN_PROGRESS":
            messages.error(
                request,
                f"Consultation can only be edited while the appointment is "
                f"'In Progress'. Current status: {appt.get_status_display()}.",
            )
            return redirect("appointments:detail", pk=appt.pk)

        mr = self._ensure_medical_record(request)
        prescription, _ = Prescription.objects.get_or_create(medical_record=mr)
        vitals, _ = Vitals.objects.get_or_create(medical_record=mr)

        mr_form = MedicalRecordForm(request.POST, instance=mr)
        vitals_form = VitalsForm(request.POST, instance=vitals)
        dx_formset = DiagnosisFormSet(request.POST, instance=mr, prefix="dx")
        rx_form = PrescriptionForm(request.POST, instance=prescription)
        rx_formset = PrescriptionItemFormSet(
            request.POST, instance=prescription, prefix="rx",
        )

        if all([
            mr_form.is_valid(),
            vitals_form.is_valid(),
            dx_formset.is_valid(),
            rx_form.is_valid(),
            rx_formset.is_valid(),
        ]):
            with transaction.atomic():
                mr = mr_form.save(commit=False)
                if not mr.created_by:
                    mr.created_by = request.user
                mr.save()

                vitals_form.instance.medical_record = mr
                if not vitals_form.instance.recorded_by:
                    vitals_form.instance.recorded_by = request.user
                vitals_form.save()

                dx_formset.save()

                rx = rx_form.save(commit=False)
                rx.medical_record = mr
                rx.save()

                rx_formset.instance = rx
                rx_formset.save()

            messages.success(request, "Consultation saved.")
            return redirect(
                "medical_records:consultation",
                appointment_pk=appt.pk,
            )

        # Not valid — re-render with errors
        return render(request, self.template_name, {
            "appointment": appt,
            "mr_form": mr_form,
            "vitals_form": vitals_form,
            "dx_formset": dx_formset,
            "rx_form": rx_form,
            "rx_formset": rx_formset,
            "is_readonly": False,
        })

    # ---------- Helpers ----------

    def _ensure_medical_record(self, request):
        mr, created = MedicalRecord.objects.get_or_create(
            appointment=self.appointment,
            defaults={"created_by": request.user},
        )
        return mr

    def _render(self, request):
        appt = self.appointment

        is_readonly = appt.status != "IN_PROGRESS"

        # Ensure records exist for editable case; for read-only, get if they exist
        if is_readonly:
            mr = MedicalRecord.objects.filter(appointment=appt).first()
            vitals = Vitals.objects.filter(medical_record=mr).first() if mr else None
            prescription = (
                Prescription.objects.filter(medical_record=mr).first() if mr else None
            )
        else:
            mr = self._ensure_medical_record(request)
            vitals, _ = Vitals.objects.get_or_create(medical_record=mr)
            prescription, _ = Prescription.objects.get_or_create(medical_record=mr)

        mr_form = MedicalRecordForm(instance=mr) if mr else MedicalRecordForm()
        vitals_form = VitalsForm(instance=vitals) if vitals else VitalsForm()
        dx_formset = DiagnosisFormSet(instance=mr, prefix="dx") if mr else DiagnosisFormSet(prefix="dx")
        rx_form = (
            PrescriptionForm(instance=prescription)
            if prescription else PrescriptionForm()
        )
        rx_formset = (
            PrescriptionItemFormSet(instance=prescription, prefix="rx")
            if prescription
            else PrescriptionItemFormSet(prefix="rx")
        )

        return render(request, self.template_name, {
            "appointment": appt,
            "mr_form": mr_form,
            "vitals_form": vitals_form,
            "dx_formset": dx_formset,
            "rx_form": rx_form,
            "rx_formset": rx_formset,
            "is_readonly": is_readonly,
        })