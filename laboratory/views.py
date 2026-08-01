# Create your views here.
"""Views for the laboratory app."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from appointments.models import Appointment
from billing.models import ServiceCatalog
from medical_records.models import MedicalRecord

from .models import LabOrder, LabOrderItem

# =========================================================
# Access mixin
# =========================================================


class LabTechOrAdminMixin(LoginRequiredMixin):
    """
    Allows LAB_TECH role users and admins.
    Used for queue + result entry (T-7.4).
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        user = request.user
        if not (user.is_admin or getattr(user, "role", None) == "LAB_TECH"):
            raise PermissionDenied("This area is restricted to lab technicians and admins.")
        return super().dispatch(request, *args, **kwargs)


# =========================================================
# T-7.3 — Doctor orders lab tests from consultation
# =========================================================


class LabOrderCreateView(LoginRequiredMixin, View):
    """
    POST-only endpoint invoked from the consultation modal.
    Access: assigned doctor OR admin, and appointment must be IN_PROGRESS.
    """

    http_method_names = ["post"]

    def post(self, request, appointment_pk, *args, **kwargs):
        appointment = get_object_or_404(Appointment, pk=appointment_pk)

        # Access check
        user = request.user
        is_owning_doctor = (
            user.role == "DOCTOR"
            and hasattr(user, "doctor_profile")
            and appointment.doctor_id == user.doctor_profile.pk
        )
        if not (user.is_admin or is_owning_doctor):
            raise PermissionDenied("Only the assigned doctor or an admin can order lab tests.")

        # State check
        if appointment.status != "IN_PROGRESS":
            messages.error(
                request,
                "Lab tests can only be ordered during an in-progress consultation.",
            )
            return redirect("medical_records:consultation", appointment_pk=appointment.pk)

        # Medical record must exist
        medical_record = MedicalRecord.objects.filter(appointment=appointment).first()
        if medical_record is None:
            messages.error(
                request,
                "No medical record exists for this appointment yet.",
            )
            return redirect("medical_records:consultation", appointment_pk=appointment.pk)

        # Service picks
        service_ids = request.POST.getlist("services")
        if not service_ids:
            messages.error(request, "Please select at least one lab test.")
            return redirect("medical_records:consultation", appointment_pk=appointment.pk)

        # Validate services (must be LABORATORY + active)
        services = list(
            ServiceCatalog.objects.filter(
                pk__in=[int(sid) for sid in service_ids if sid.isdigit()],
                category=ServiceCatalog.Category.LABORATORY,
                is_active=True,
            )
        )
        if not services:
            messages.error(request, "No valid lab tests were selected.")
            return redirect("medical_records:consultation", appointment_pk=appointment.pk)

        clinical_notes = request.POST.get("clinical_notes", "").strip()

        # Create the order + items
        order = LabOrder.objects.create(
            medical_record=medical_record,
            patient=appointment.patient,
            clinical_notes=clinical_notes,
            ordered_by=user,
        )
        for service in services:
            LabOrderItem.objects.create(
                order=order,
                service=service,
                unit_price=service.default_price,
            )

        messages.success(
            request,
            f"Lab order {order.order_number} created with {len(services)} test(s).",
        )
        return redirect("medical_records:consultation", appointment_pk=appointment.pk)


# =========================================================
# T-7.4 — Lab technician queue + result entry
# =========================================================


class LabQueueView(LabTechOrAdminMixin, ListView):
    """Non-terminal lab orders grouped by status. Lab-tech + admin."""

    template_name = "laboratory/queue.html"
    context_object_name = "orders"
    paginate_by = 50

    def get_queryset(self):
        return (
            LabOrder.objects.exclude(status__in=["COMPLETED", "CANCELLED"])
            .select_related(
                "patient",
                "medical_record__appointment__doctor__user",
                "ordered_by",
            )
            .prefetch_related("items__service")
            .order_by("status", "created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Bucket by status for grouped display
        buckets = {"ORDERED": [], "SAMPLE_COLLECTED": [], "IN_PROGRESS": []}
        for order in ctx["orders"]:
            if order.status in buckets:
                buckets[order.status].append(order)
        ctx["buckets"] = [
            {"status": "ORDERED", "label": "Awaiting Sample", "orders": buckets["ORDERED"]},
            {
                "status": "SAMPLE_COLLECTED",
                "label": "Sample Collected",
                "orders": buckets["SAMPLE_COLLECTED"],
            },
            {"status": "IN_PROGRESS", "label": "In Progress", "orders": buckets["IN_PROGRESS"]},
        ]
        return ctx


class LabOrderDetailView(LabTechOrAdminMixin, DetailView):
    """Detail + result-entry page. Lab-tech + admin."""

    model = LabOrder
    template_name = "laboratory/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return LabOrder.objects.select_related(
            "patient",
            "medical_record__appointment__doctor__user",
            "medical_record__appointment__doctor__department",
            "ordered_by",
        ).prefetch_related("items__service__lab_profile")


class LabOrderTransitionView(LabTechOrAdminMixin, View):
    """POST-only state transition: ORDERED → SAMPLE_COLLECTED → IN_PROGRESS → COMPLETED (or CANCELLED)."""

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(LabOrder, pk=pk)
        new_status = request.POST.get("new_status", "").strip()

        if not order.can_transition_to(new_status):
            messages.error(
                request,
                f"Cannot transition from {order.get_status_display()} to {new_status}.",
            )
            return redirect("laboratory:order_detail", pk=order.pk)

        # When completing, ensure at least one item has a result
        if new_status == "COMPLETED":
            if not order.items.exclude(result_value="").exists():
                messages.error(
                    request,
                    "At least one item must have a result before completing the order.",
                )
                return redirect("laboratory:order_detail", pk=order.pk)

        # Cancel needs a reason
        if new_status == "CANCELLED":
            reason = request.POST.get("cancelled_reason", "").strip()
            if not reason:
                messages.error(request, "A cancellation reason is required.")
                return redirect("laboratory:order_detail", pk=order.pk)
            order.cancelled_reason = reason
            order.cancelled_at = timezone.now()

        # Sample collected timestamp
        if new_status == "SAMPLE_COLLECTED":
            order.sample_collected_at = timezone.now()

        order.status = new_status
        order.save()
        # The signal in laboratory/signals.py handles auto-billing on COMPLETED.

        messages.success(
            request,
            f"Order {order.order_number} marked as {order.get_status_display()}.",
        )
        return redirect("laboratory:order_detail", pk=order.pk)


class LabResultEntryView(LabTechOrAdminMixin, View):
    """Save results for one order's items. POST-only."""

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        order = get_object_or_404(LabOrder, pk=pk)

        if order.is_terminal:
            messages.error(request, "Cannot edit results on a terminal order.")
            return redirect("laboratory:order_detail", pk=order.pk)

        # Advance ORDERED → IN_PROGRESS silently on first result entry
        # (skip if already in a later state)
        updated_count = 0
        for item in order.items.all():
            prefix = f"item-{item.pk}-"
            value = request.POST.get(f"{prefix}result_value", "").strip()
            notes = request.POST.get(f"{prefix}result_notes", "").strip()
            is_abnormal = request.POST.get(f"{prefix}is_abnormal") == "on"

            changed = False
            if value and value != item.result_value:
                item.result_value = value
                changed = True
            if notes != item.result_notes:
                item.result_notes = notes
                changed = True
            if is_abnormal != item.is_abnormal:
                item.is_abnormal = is_abnormal
                changed = True

            if changed:
                if value and not item.resulted_at:
                    item.resulted_at = timezone.now()
                    item.resulted_by = request.user
                item.save()
                updated_count += 1

        # Auto-advance state if we're still in early states
        if updated_count > 0 and order.status in ("ORDERED", "SAMPLE_COLLECTED"):
            order.status = "IN_PROGRESS"
            order.save()

        if updated_count:
            messages.success(request, f"Saved results for {updated_count} item(s).")
        else:
            messages.info(request, "No changes to save.")

        return redirect("laboratory:order_detail", pk=order.pk)


class LabReportPdfView(LoginRequiredMixin, DetailView):
    """Render a completed lab order as a downloadable PDF.

    Access:
      - Owning doctor
      - Admin
      - Lab technician
      - Patient owning the order (COMPLETED only)
    """

    model = LabOrder
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return LabOrder.objects.select_related(
            "patient",
            "medical_record__appointment__doctor__user",
            "medical_record__appointment__doctor__department",
        ).prefetch_related(
            "items__service__lab_profile",
            "items__resulted_by",
        )

    def get(self, request, *args, **kwargs):
        from common.pdf_utils import render_pdf

        order = self.get_object()
        user = request.user

        # Only completed orders may be printed
        if order.status != "COMPLETED":
            raise PermissionDenied("Lab reports are available only for completed orders.")

        is_owning_doctor = (
            user.role == "DOCTOR"
            and hasattr(user, "doctor_profile")
            and order.medical_record.appointment.doctor_id == user.doctor_profile.pk
        )
        is_owning_patient = (
            user.role == "PATIENT"
            and hasattr(user, "patient_profile")
            and order.patient_id == user.patient_profile.pk
        )
        is_lab_tech = getattr(user, "role", None) == "LAB_TECH"

        if not (user.is_admin or is_owning_doctor or is_owning_patient or is_lab_tech):
            raise PermissionDenied("You do not have access to this lab report.")

        filename = f"lab-{order.order_number}.pdf"
        return render_pdf(
            "laboratory/lab_report_pdf.html",
            {"order": order},
            filename,
        )
