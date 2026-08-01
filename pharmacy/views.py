"""Views for the pharmacy app."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from medical_records.models import Prescription

from .models import Dispense, DispenseItem, InventoryItem

# =========================================================
# Access mixin + low-stock helper (T-7.7)
# =========================================================


class PharmacistOrAdminMixin(LoginRequiredMixin):
    """Allow PHARMACIST and ADMIN roles."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        user = request.user
        if not (user.is_admin or getattr(user, "role", None) == "PHARMACIST"):
            raise PermissionDenied("This area is restricted to pharmacists and admins.")
        return super().dispatch(request, *args, **kwargs)


def low_stock_items():
    """Queryset of InventoryItem where quantity_on_hand ≤ reorder_threshold."""
    from django.db.models import F

    return InventoryItem.objects.filter(
        quantity_on_hand__lte=F("reorder_threshold"),
    ).select_related("medication")


# =========================================================
# T-7.9 — Pharmacy queue + dispense flow
# =========================================================


class PharmacyQueueView(PharmacistOrAdminMixin, ListView):
    """
    Prescriptions awaiting dispense.

    Shows prescriptions from completed appointments where either:
      - No dispense exists yet, or
      - Latest dispense is PENDING or CANCELLED (so patient still needs meds)
    """

    template_name = "pharmacy/queue.html"
    context_object_name = "prescriptions"
    paginate_by = 50

    def get_queryset(self):
        return (
            Prescription.objects.filter(
                medical_record__appointment__status="COMPLETED",
                items__isnull=False,
            )
            .exclude(
                # Exclude prescriptions with any DISPENSED dispense
                dispenses__status="DISPENSED",
            )
            .distinct()
            .select_related(
                "medical_record__appointment__patient",
                "medical_record__appointment__doctor__user",
            )
            .prefetch_related("items__medication")
            .order_by("-medical_record__appointment__scheduled_start")
        )


class DispenseCreateView(PharmacistOrAdminMixin, View):
    """
    GET: show the dispense form for a prescription.
    POST: create Dispense + items, then mark_dispensed().
    """

    template_name = "pharmacy/dispense_form.html"

    def get(self, request, prescription_pk, *args, **kwargs):
        prescription = self._get_prescription(prescription_pk)
        rows = self._build_rows(prescription)
        return self._render(request, prescription, rows)

    def post(self, request, prescription_pk, *args, **kwargs):
        prescription = self._get_prescription(prescription_pk)
        rows = self._build_rows(prescription)

        # Parse posted values into rows
        selected_rows = []
        for row in rows:
            prefix = f"item-{row['prescription_item'].pk}-"
            inv_id_raw = request.POST.get(f"{prefix}inventory_id", "").strip()
            qty_raw = request.POST.get(f"{prefix}quantity", "0").strip()

            if not inv_id_raw or not qty_raw:
                continue

            try:
                qty = int(qty_raw)
            except ValueError:
                continue
            if qty <= 0:
                continue

            inv = InventoryItem.objects.filter(pk=int(inv_id_raw)).first()
            if inv is None:
                continue

            selected_rows.append(
                {
                    "prescription_item": row["prescription_item"],
                    "inventory_item": inv,
                    "quantity": qty,
                }
            )

        if not selected_rows:
            messages.error(request, "Please dispense at least one item.")
            return self._render(request, prescription, rows)

        notes = request.POST.get("notes", "").strip()

        # Create + dispense atomically
        try:
            with transaction.atomic():
                dispense = Dispense.objects.create(
                    prescription=prescription,
                    patient=prescription.medical_record.appointment.patient,
                    notes=notes,
                )
                for sel in selected_rows:
                    DispenseItem.objects.create(
                        dispense=dispense,
                        prescription_item=sel["prescription_item"],
                        inventory_item=sel["inventory_item"],
                        quantity_dispensed=sel["quantity"],
                    )
                dispense.mark_dispensed(user=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return self._render(request, prescription, rows)

        messages.success(
            request,
            f"Dispense {dispense.dispense_number} completed. "
            f"Inventory drawn down for {len(selected_rows)} item(s).",
        )
        return redirect("pharmacy:dispense_detail", pk=dispense.pk)

    # ---------- Helpers ----------

    def _get_prescription(self, pk):
        return get_object_or_404(
            Prescription.objects.select_related(
                "medical_record__appointment__patient",
                "medical_record__appointment__doctor__user",
            ).prefetch_related("items__medication"),
            pk=pk,
        )

    def _build_rows(self, prescription):
        """One row per prescription item, with the matching inventory item."""
        rows = []
        for item in prescription.items.all():
            inv = InventoryItem.objects.filter(medication=item.medication).first()
            rows.append(
                {
                    "prescription_item": item,
                    "inventory_item": inv,  # May be None (not in inventory)
                    "in_stock": inv.quantity_on_hand if inv else 0,
                    "low_stock": inv.is_low_stock if inv else False,
                }
            )
        return rows

    def _render(self, request, prescription, rows):
        from django.shortcuts import render

        return render(
            request,
            self.template_name,
            {
                "prescription": prescription,
                "rows": rows,
            },
        )


class DispenseDetailView(PharmacistOrAdminMixin, DetailView):
    """Read-only dispense receipt."""

    model = Dispense
    template_name = "pharmacy/dispense_detail.html"
    context_object_name = "dispense"

    def get_queryset(self):
        return Dispense.objects.select_related(
            "patient",
            "prescription__medical_record__appointment__doctor__user",
            "dispensed_by",
        ).prefetch_related("items__inventory_item__medication")


# =========================================================
# T-7.10 — Inventory management
# =========================================================


class InventoryListView(PharmacistOrAdminMixin, ListView):
    """Inventory list with search + low-stock filter."""

    template_name = "pharmacy/inventory_list.html"
    context_object_name = "items"
    paginate_by = 30

    def get_queryset(self):
        qs = InventoryItem.objects.select_related("medication")

        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(medication__name__icontains=search)

        low_only = self.request.GET.get("low", "").strip()
        if low_only == "1":
            from django.db.models import F

            qs = qs.filter(quantity_on_hand__lte=F("reorder_threshold"))

        return qs.order_by("medication__name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search"] = self.request.GET.get("q", "").strip()
        ctx["low_only"] = self.request.GET.get("low", "").strip() == "1"
        ctx["low_stock_total"] = low_stock_items().count()
        return ctx


class InventoryReceiveView(PharmacistOrAdminMixin, View):
    """POST-only: add stock (RECEIVE movement)."""

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        item = get_object_or_404(InventoryItem, pk=pk)
        qty_raw = request.POST.get("quantity", "").strip()
        reference = request.POST.get("reference", "").strip()

        try:
            qty = int(qty_raw)
        except ValueError:
            messages.error(request, "Quantity must be a whole number.")
            return redirect("pharmacy:inventory_list")

        if qty <= 0:
            messages.error(request, "Received quantity must be > 0.")
            return redirect("pharmacy:inventory_list")

        try:
            item.apply_movement(
                movement_type="RECEIVE",
                quantity=qty,
                performed_by=request.user,
                reference=reference,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("pharmacy:inventory_list")

        messages.success(
            request,
            f"Received {qty} × {item.medication.name}. New stock: {item.quantity_on_hand}.",
        )
        return redirect("pharmacy:inventory_list")


class InventoryAdjustView(PharmacistOrAdminMixin, View):
    """POST-only: signed adjustment (ADJUST movement)."""

    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        item = get_object_or_404(InventoryItem, pk=pk)
        qty_raw = request.POST.get("quantity", "").strip()
        reason = request.POST.get("reason", "").strip()

        try:
            qty = int(qty_raw)
        except ValueError:
            messages.error(request, "Adjustment must be a whole number.")
            return redirect("pharmacy:inventory_list")

        if qty == 0:
            messages.error(request, "Adjustment cannot be zero.")
            return redirect("pharmacy:inventory_list")

        if not reason:
            messages.error(request, "A reason is required for adjustments.")
            return redirect("pharmacy:inventory_list")

        try:
            item.apply_movement(
                movement_type="ADJUST",
                quantity=qty,
                performed_by=request.user,
                reason=reason,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("pharmacy:inventory_list")

        sign = "+" if qty > 0 else ""
        messages.success(
            request,
            f"Adjusted {item.medication.name} by {sign}{qty}. New stock: {item.quantity_on_hand}.",
        )
        return redirect("pharmacy:inventory_list")


class InventoryMovementsView(PharmacistOrAdminMixin, DetailView):
    """Movement history for one inventory item."""

    model = InventoryItem
    template_name = "pharmacy/inventory_movements.html"
    context_object_name = "item"

    def get_queryset(self):
        return InventoryItem.objects.select_related("medication").prefetch_related(
            "movements__performed_by",
        )
