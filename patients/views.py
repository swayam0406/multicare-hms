from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView

from accounts.mixins import (
    AdminRequiredMixin,
    PatientRequiredMixin,
    StaffRequiredMixin,
)

from .forms import PatientForm
from .models import Patient


class PatientListView(StaffRequiredMixin, ListView):
    """Paginated list of patients with search + active/inactive filter. Staff only."""

    model = Patient
    template_name = "patients/patient_list.html"
    context_object_name = "patients"
    paginate_by = 20

    def get_queryset(self):
        show = self.request.GET.get("show", "active")
        if show == "inactive":
            qs = Patient.objects.inactive()
        elif show == "all":
            qs = Patient.objects.all()
        else:  # default: active
            qs = Patient.objects.active()

        qs = qs.select_related("registered_by").order_by("-created_at")

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(patient_id__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(phone__icontains=query)
                | Q(email__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["total_active"] = Patient.objects.active().count()
        ctx["total_inactive"] = Patient.objects.inactive().count()
        ctx["search_query"] = self.request.GET.get("q", "").strip()
        ctx["show_filter"] = self.request.GET.get("show", "active")
        return ctx


class PatientCreateView(StaffRequiredMixin, CreateView):
    """Register a new patient. Restricted to hospital staff."""

    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_form.html"
    success_url = reverse_lazy("patients:list")

    def form_valid(self, form):
        form.instance.registered_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Patient {self.object.full_name} registered successfully "
            f"with ID {self.object.patient_id}.",
        )
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Register New Patient"
        ctx["submit_label"] = "Register Patient"
        return ctx


class PatientDetailView(StaffRequiredMixin, DetailView):
    """Display full patient information. Staff only."""

    model = Patient
    template_name = "patients/patient_detail.html"
    context_object_name = "patient"
    slug_field = "patient_id"
    slug_url_kwarg = "patient_id"

    def get_queryset(self):
        return Patient.objects.select_related("registered_by", "user")


class PatientUpdateView(StaffRequiredMixin, UpdateView):
    """Edit an existing patient. Staff only."""

    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_form.html"
    slug_field = "patient_id"
    slug_url_kwarg = "patient_id"
    context_object_name = "patient"

    def get_success_url(self):
        return reverse("patients:detail", kwargs={"patient_id": self.object.patient_id})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Patient {self.object.full_name} ({self.object.patient_id}) " f"updated successfully.",
        )
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Edit Patient — {self.object.full_name}"
        ctx["submit_label"] = "Save Changes"
        ctx["is_edit"] = True
        return ctx


class PatientToggleActiveView(AdminRequiredMixin, View):
    """
    Toggle a patient's active state (soft delete / restore).
    Admin only. POST-only for CSRF safety.
    """

    http_method_names = ["post"]

    def post(self, request, patient_id, *args, **kwargs):
        patient = get_object_or_404(Patient, patient_id=patient_id)
        patient.is_active = not patient.is_active
        patient.save(update_fields=["is_active", "updated_at"])

        if patient.is_active:
            messages.success(
                request,
                f"Patient {patient.full_name} ({patient.patient_id}) has been reactivated.",
            )
        else:
            messages.warning(
                request,
                f"Patient {patient.full_name} ({patient.patient_id}) has been deactivated. "
                f"The record is preserved but hidden from the active list.",
            )
        return redirect("patients:detail", patient_id=patient.patient_id)


class MyPatientRecordView(PatientRequiredMixin, DetailView):
    """
    Self-service view: a logged-in patient views their own record.
    Uses the same detail template as staff, with self-view context.
    """

    model = Patient
    template_name = "patients/patient_detail.html"
    context_object_name = "patient"

    def get_object(self, queryset=None):
        try:
            return Patient.objects.select_related(
                "registered_by", "user"
            ).get(user=self.request.user)
        except Patient.DoesNotExist as err:
            raise Http404(
                "No patient record is linked to your account. "
                "Please contact hospital reception."
            ) from err

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_self_view"] = True
        return ctx
