"""Views for the core app."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.mixins import AdminRequiredMixin

CACHE_TTL = 60  # seconds


class HomeView(TemplateView):
    """Public / logged-in landing page."""

    template_name = "core/home.html"


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """Admin-only at-a-glance dashboard. Cached 60s."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stats"] = _get_dashboard_stats()
        ctx["today"] = timezone.localdate()
        return ctx


def _get_dashboard_stats() -> dict:
    """Assemble today's dashboard numbers. Cached as one blob."""
    cached = cache.get("admin_dashboard_stats")
    if cached is not None:
        return cached

    from django.db.models import F

    from appointments.models import Appointment
    from billing.models import Bill, Payment
    from laboratory.models import LabOrder
    from patients.models import Patient
    from pharmacy.models import Dispense, InventoryItem

    today = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    day_end = day_start + timedelta(days=1)

    # ---------- Appointments ----------
    appts_today = Appointment.objects.filter(
        scheduled_start__gte=day_start,
        scheduled_start__lt=day_end,
    )
    appts_status = dict(appts_today.values_list("status").annotate(n=Count("id")))

    # ---------- Billing ----------
    bills_draft = Bill.objects.filter(status="DRAFT").count()
    bills_outstanding = Bill.objects.filter(
        status__in=["FINALIZED", "PARTIAL"],
    ).count()

    revenue_today = Payment.objects.filter(
        status="COMPLETED",
        received_at__gte=day_start,
        received_at__lt=day_end,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    # ---------- Pharmacy ----------
    dispenses_today = Dispense.objects.filter(
        status="DISPENSED",
        dispensed_at__gte=day_start,
        dispensed_at__lt=day_end,
    ).count()

    low_stock_count = InventoryItem.objects.filter(
        quantity_on_hand__lte=F("reorder_threshold"),
    ).count()

    # ---------- Lab ----------
    labs_today = LabOrder.objects.filter(
        created_at__gte=day_start,
        created_at__lt=day_end,
    ).count()

    labs_pending = LabOrder.objects.exclude(
        status__in=["COMPLETED", "CANCELLED"],
    ).count()

    # ---------- Patients ----------
    new_patients_today = Patient.objects.filter(
        created_at__gte=day_start,
        created_at__lt=day_end,
    ).count()

    total_active_patients = Patient.objects.filter(is_active=True).count()

    stats = {
        "appointments": {
            "total": appts_today.count(),
            "scheduled": appts_status.get("SCHEDULED", 0),
            "confirmed": appts_status.get("CONFIRMED", 0),
            "in_progress": appts_status.get("IN_PROGRESS", 0),
            "completed": appts_status.get("COMPLETED", 0),
            "cancelled": appts_status.get("CANCELLED", 0),
            "no_show": appts_status.get("NO_SHOW", 0),
        },
        "billing": {
            "drafts": bills_draft,
            "outstanding": bills_outstanding,
            "revenue_today": revenue_today,
        },
        "pharmacy": {
            "dispenses_today": dispenses_today,
            "low_stock": low_stock_count,
        },
        "lab": {
            "orders_today": labs_today,
            "pending": labs_pending,
        },
        "patients": {
            "new_today": new_patients_today,
            "total_active": total_active_patients,
        },
    }

    cache.set("admin_dashboard_stats", stats, CACHE_TTL)
    return stats
