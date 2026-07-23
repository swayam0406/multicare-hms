"""Views for the appointments app."""

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView

from accounts.mixins import (
    DoctorRequiredMixin,
    PatientRequiredMixin,
    StaffRequiredMixin,
)
from doctors.models import Doctor

from .forms import AppointmentForm
from .models import Appointment
from .services import available_slots


class AvailableSlotsView(StaffRequiredMixin, View):
    """JSON endpoint used by the booking form to populate the time dropdown."""

    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        doctor_id = request.GET.get("doctor")
        date_str = request.GET.get("date")

        if not doctor_id or not date_str:
            return JsonResponse({"slots": [], "error": "Missing parameters."}, status=400)

        try:
            doctor = Doctor.objects.get(pk=doctor_id, is_available_for_booking=True)
        except (Doctor.DoesNotExist, ValueError):
            return JsonResponse({"slots": [], "error": "Doctor not found."}, status=404)

        try:
            on_date = date.fromisoformat(date_str)
        except ValueError:
            return JsonResponse({"slots": [], "error": "Invalid date."}, status=400)

        if on_date < timezone.localdate():
            return JsonResponse({"slots": [], "error": "Date is in the past."}, status=400)

        return JsonResponse({"slots": available_slots(doctor, on_date)})


class AppointmentListView(StaffRequiredMixin, ListView):
    """Paginated appointment list with filters. Staff only."""

    model = Appointment
    template_name = "appointments/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 25

    def get_queryset(self):
        qs = Appointment.objects.select_related(
            "patient", "doctor__user", "doctor__department", "booked_by"
        )

        date_from_str = self.request.GET.get("date_from", "").strip()
        date_to_str = self.request.GET.get("date_to", "").strip()
        quick = self.request.GET.get("quick", "").strip()

        today = timezone.localdate()
        if quick == "today":
            date_from_str = date_to_str = today.isoformat()
        elif quick == "tomorrow":
            tomorrow = today + timedelta(days=1)
            date_from_str = date_to_str = tomorrow.isoformat()
        elif quick == "week":
            date_from_str = today.isoformat()
            date_to_str = (today + timedelta(days=6)).isoformat()
        elif quick == "past":
            date_from_str = (today - timedelta(days=30)).isoformat()
            date_to_str = (today - timedelta(days=1)).isoformat()

        date_from = self._parse_date(date_from_str)
        date_to = self._parse_date(date_to_str)

        if date_from:
            qs = qs.filter(scheduled_start__date__gte=date_from)
        if date_to:
            qs = qs.filter(scheduled_start__date__lte=date_to)

        doctor_id = self.request.GET.get("doctor", "").strip()
        if doctor_id.isdigit():
            qs = qs.filter(doctor_id=int(doctor_id))

        status = self.request.GET.get("status", "").strip()
        if status in dict(Appointment.Status.choices):
            qs = qs.filter(status=status)

        return qs.order_by("scheduled_start")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        doctor_raw = self.request.GET.get("doctor", "").strip()
        selected_doctor_id = int(doctor_raw) if doctor_raw.isdigit() else 0

        doctors = list(
            Doctor.objects.select_related("user", "department").order_by("user__first_name")
        )
        for doc in doctors:
            doc.is_selected = doc.pk == selected_doctor_id
        ctx["doctors"] = doctors

        selected_status = self.request.GET.get("status", "").strip()
        ctx["statuses"] = [
            {"value": v, "label": lbl, "is_selected": v == selected_status}
            for v, lbl in Appointment.Status.choices
        ]

        ctx["filters"] = {
            "date_from": self.request.GET.get("date_from", "").strip(),
            "date_to": self.request.GET.get("date_to", "").strip(),
            "doctor": doctor_raw,
            "status": selected_status,
            "quick": self.request.GET.get("quick", "").strip(),
        }
        return ctx

    @staticmethod
    def _parse_date(s):
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None


class AppointmentCreateView(StaffRequiredMixin, CreateView):
    """Book a new appointment. Staff only."""

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:list")

    def form_valid(self, form):
        form.instance.booked_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Appointment booked: {self.object.patient.full_name} with "
            f"{self.object.doctor.display_name} on "
            f"{timezone.localtime(self.object.scheduled_start):%b %d, %Y at %I:%M %p}.",
        )
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Book Appointment"
        ctx["submit_label"] = "Book Appointment"
        return ctx


class DoctorQueueView(DoctorRequiredMixin, TemplateView):
    """A doctor's daily patient queue."""

    template_name = "appointments/doctor_queue.html"

    def get_context_data(self, **kwargs):
        if not hasattr(self.request.user, "doctor_profile"):
            raise Http404("No doctor profile is linked to your account. Please contact admin.")

        ctx = super().get_context_data(**kwargs)
        doctor = self.request.user.doctor_profile

        date_str = self.request.GET.get("date", "").strip()
        selected_date = timezone.localdate()
        if date_str:
            try:
                selected_date = date.fromisoformat(date_str)
            except ValueError:
                pass

        day_start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)

        appointments = (
            Appointment.objects.filter(
                doctor=doctor,
                scheduled_start__gte=day_start,
                scheduled_start__lt=day_end,
            )
            .select_related("patient")
            .order_by("scheduled_start")
        )

        counts = {status.value: 0 for status in Appointment.Status}
        for appt in appointments:
            counts[appt.status] = counts.get(appt.status, 0) + 1

        prev_date = selected_date - timedelta(days=1)
        next_date = selected_date + timedelta(days=1)

        ctx.update(
            {
                "doctor": doctor,
                "selected_date": selected_date,
                "is_today": selected_date == timezone.localdate(),
                "prev_date": prev_date,
                "next_date": next_date,
                "appointments": appointments,
                "total": appointments.count(),
                "counts": counts,
            }
        )
        return ctx


class AppointmentDetailView(StaffRequiredMixin, DetailView):
    """Read-only detail page showing all appointment info + status actions."""

    model = Appointment
    template_name = "appointments/appointment_detail.html"
    context_object_name = "appointment"

    def get_queryset(self):
        return Appointment.objects.select_related(
            "patient", "doctor__user", "doctor__department", "booked_by"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        appt = self.object
        user = self.request.user

        is_own_appointment = (
            user.role == "DOCTOR"
            and hasattr(user, "doctor_profile")
            and appt.doctor_id == user.doctor_profile.pk
        )
        ctx["can_start_or_complete"] = user.is_admin or is_own_appointment
        ctx["available_transitions"] = appt.available_transitions()
        return ctx


class AppointmentTransitionView(StaffRequiredMixin, View):
    """Transition an appointment to a new status. POST only."""

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        appt = get_object_or_404(Appointment, pk=pk)
        new_status = request.POST.get("new_status", "").strip()

        if not appt.can_transition_to(new_status):
            messages.error(
                request,
                f"Cannot change appointment from '{appt.get_status_display()}' "
                f"to '{new_status}'.",
            )
            return redirect("appointments:detail", pk=appt.pk)

        clinical_actions = {"IN_PROGRESS", "COMPLETED", "NO_SHOW"}
        user = request.user
        if new_status in clinical_actions and not user.is_admin:
            if not (
                user.role == "DOCTOR"
                and hasattr(user, "doctor_profile")
                and appt.doctor_id == user.doctor_profile.pk
            ):
                raise PermissionDenied(
                    "Only the assigned doctor or an admin can perform this action."
                )

        if new_status == "CANCELLED":
            reason = request.POST.get("cancelled_reason", "").strip()
            if not reason:
                messages.error(request, "Cancellation reason is required.")
                return redirect("appointments:detail", pk=appt.pk)
            appt.cancelled_reason = reason

        note_text = request.POST.get("notes", "").strip()
        if note_text:
            timestamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
            actor = user.get_full_name() or user.username
            entry = f"[{timestamp} — {actor}] {note_text}"
            appt.notes = (appt.notes + "\n\n" + entry).strip() if appt.notes else entry

        appt.status = new_status
        appt.save(update_fields=["status", "notes", "cancelled_reason", "updated_at"])

        messages.success(
            request,
            f"Appointment marked as {appt.get_status_display()}.",
        )
        return redirect("appointments:detail", pk=appt.pk)


class MyAppointmentsView(PatientRequiredMixin, TemplateView):
    """Self-service view — patients see their own upcoming and past appointments."""

    template_name = "appointments/my_appointments.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        if not hasattr(user, "patient_profile"):
            raise Http404(
                "No patient record is linked to your account. " "Please contact hospital reception."
            )

        ctx = super().get_context_data(**kwargs)
        patient = user.patient_profile
        now = timezone.now()

        base_qs = Appointment.objects.filter(patient=patient).select_related(
            "doctor__user", "doctor__department"
        )

        upcoming = (
            base_qs.filter(scheduled_start__gte=now)
            .exclude(status__in=("CANCELLED", "COMPLETED", "NO_SHOW"))
            .order_by("scheduled_start")
        )
        past = base_qs.filter(scheduled_start__lt=now).order_by("-scheduled_start")

        ctx.update(
            {
                "patient": patient,
                "upcoming": upcoming,
                "past": past,
                "upcoming_count": upcoming.count(),
                "past_count": past.count(),
            }
        )
        return ctx
