"""Views for the billing app."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from accounts.mixins import StaffRequiredMixin

from .models import Bill, BillItem, InsuranceClaim, Payment, ServiceCatalog


class BillListView(StaffRequiredMixin, ListView):
    """Paginated bill list with filters. Staff only."""

    model = Bill
    template_name = "billing/bill_list.html"
    context_object_name = "bills"
    paginate_by = 25

    def get_queryset(self):
        qs = Bill.objects.select_related("patient", "appointment__doctor__user")

        date_from_str = self.request.GET.get("date_from", "").strip()
        date_to_str = self.request.GET.get("date_to", "").strip()
        quick = self.request.GET.get("quick", "").strip()

        today = timezone.localdate()
        if quick == "today":
            date_from_str = date_to_str = today.isoformat()
        elif quick == "week":
            date_from_str = (today - timedelta(days=6)).isoformat()
            date_to_str = today.isoformat()
        elif quick == "month":
            date_from_str = (today - timedelta(days=30)).isoformat()
            date_to_str = today.isoformat()
        elif quick == "outstanding":
            date_from_str = ""
            date_to_str = ""

        date_from = self._parse_date(date_from_str)
        date_to = self._parse_date(date_to_str)

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        status = self.request.GET.get("status", "").strip()
        if status in dict(Bill.Status.choices):
            qs = qs.filter(status=status)

        if quick == "outstanding":
            qs = qs.filter(status__in=["FINALIZED", "PARTIAL"])

        patient_search = self.request.GET.get("patient", "").strip()
        if patient_search:
            qs = qs.filter(
                Q(patient__first_name__icontains=patient_search)
                | Q(patient__last_name__icontains=patient_search)
                | Q(patient__patient_id__icontains=patient_search)
                | Q(bill_number__icontains=patient_search)
            )

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_status = self.request.GET.get("status", "").strip()
        ctx["statuses"] = [
            {"value": v, "label": lbl, "is_selected": v == selected_status}
            for v, lbl in Bill.Status.choices
        ]

        ctx["filters"] = {
            "date_from": self.request.GET.get("date_from", "").strip(),
            "date_to": self.request.GET.get("date_to", "").strip(),
            "patient": self.request.GET.get("patient", "").strip(),
            "status": selected_status,
            "quick": self.request.GET.get("quick", "").strip(),
        }

        summary_qs = self.get_queryset()
        totals = summary_qs.aggregate(total_billed=Sum("total"))
        ctx["summary"] = {
            "count": summary_qs.count(),
            "total_billed": totals["total_billed"] or Decimal("0.00"),
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


class BillDetailView(StaffRequiredMixin, DetailView):
    """Bill detail with items, payments, refunds, insurance claims."""

    model = Bill
    template_name = "billing/bill_detail.html"
    context_object_name = "bill"
    slug_field = "bill_number"
    slug_url_kwarg = "bill_number"

    def get_queryset(self):
        return Bill.objects.select_related(
            "patient",
            "appointment__doctor__user",
            "appointment__doctor__department",
            "created_by",
            "finalized_by",
        ).prefetch_related(
            "items__service",
            Prefetch(
                "payments",
                queryset=Payment.objects.select_related("received_by").prefetch_related("refunds"),
            ),
            "insurance_claims",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bill = self.object

        running = bill.total
        payment_rows = []
        for payment in bill.payments.all().order_by("received_at", "created_at"):
            if payment.status == "COMPLETED":
                running = running - payment.net_amount
            payment_rows.append(
                {
                    "payment": payment,
                    "running_balance": running,
                }
            )

        ctx["payment_rows"] = payment_rows
        ctx["can_add_items"] = bill.can_edit_items()
        ctx["can_finalize"] = bill.status == "DRAFT" and bill.items.exists()
        ctx["can_record_payment"] = bill.accepts_payments() and bill.balance > Decimal("0.00")
        ctx["services"] = ServiceCatalog.objects.filter(is_active=True).order_by("category", "code")
        return ctx


# ==========================================
# Action views
# ==========================================


class BillActionMixin(StaffRequiredMixin, View):
    """Common bootstrap: load bill by number, handle POST only."""

    http_method_names = ["post"]

    def get_bill(self, bill_number):
        return get_object_or_404(Bill, bill_number=bill_number)

    def redirect_to_detail(self, bill):
        return redirect("billing:detail", bill_number=bill.bill_number)


class BillItemAddView(BillActionMixin):
    """Add a line item to a DRAFT bill."""

    def post(self, request, bill_number, *args, **kwargs):
        bill = self.get_bill(bill_number)

        if not bill.can_edit_items():
            messages.error(request, "Items can only be added to a draft bill.")
            return self.redirect_to_detail(bill)

        service_id = request.POST.get("service", "").strip()
        quantity_raw = request.POST.get("quantity", "1").strip() or "1"
        unit_price_raw = request.POST.get("unit_price", "").strip()
        description = request.POST.get("description", "").strip()

        if not service_id.isdigit():
            messages.error(request, "Please select a service.")
            return self.redirect_to_detail(bill)

        try:
            service = ServiceCatalog.objects.get(pk=int(service_id), is_active=True)
        except ServiceCatalog.DoesNotExist:
            messages.error(request, "Selected service not found.")
            return self.redirect_to_detail(bill)

        try:
            quantity = int(quantity_raw)
        except ValueError:
            messages.error(request, "Quantity must be a whole number.")
            return self.redirect_to_detail(bill)
        if quantity < 1:
            messages.error(request, "Quantity must be at least 1.")
            return self.redirect_to_detail(bill)

        unit_price = None
        if unit_price_raw:
            try:
                unit_price = Decimal(unit_price_raw)
            except (InvalidOperation, ValueError):
                messages.error(request, "Unit price must be a valid amount.")
                return self.redirect_to_detail(bill)
            if unit_price < Decimal("0.00"):
                messages.error(request, "Unit price cannot be negative.")
                return self.redirect_to_detail(bill)

        item = BillItem(
            bill=bill,
            service=service,
            quantity=quantity,
        )
        if unit_price is not None:
            item.unit_price = unit_price
        if description:
            item.description = description
        item.save()

        messages.success(request, f"Added {service.name} to the bill.")
        return self.redirect_to_detail(bill)


class BillItemDeleteView(BillActionMixin):
    """Remove a line item from a DRAFT bill."""

    def post(self, request, bill_number, item_pk, *args, **kwargs):
        bill = self.get_bill(bill_number)

        if not bill.can_edit_items():
            messages.error(request, "Items can only be removed from a draft bill.")
            return self.redirect_to_detail(bill)

        item = get_object_or_404(BillItem, pk=item_pk, bill=bill)
        item_name = item.display_name
        item.delete()

        messages.success(request, f"Removed {item_name} from the bill.")
        return self.redirect_to_detail(bill)


class BillFinalizeView(BillActionMixin):
    """Move DRAFT → FINALIZED."""

    def post(self, request, bill_number, *args, **kwargs):
        bill = self.get_bill(bill_number)
        try:
            bill.finalize(user=request.user)
            messages.success(
                request,
                f"Bill {bill.bill_number} finalized. Total: ₹{bill.total}",
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return self.redirect_to_detail(bill)


class PaymentAddView(BillActionMixin):
    """Record a payment against a FINALIZED / PARTIAL / PAID bill."""

    def post(self, request, bill_number, *args, **kwargs):
        bill = self.get_bill(bill_number)

        if not bill.accepts_payments():
            messages.error(
                request,
                f"Payments cannot be recorded against a {bill.get_status_display()} bill.",
            )
            return self.redirect_to_detail(bill)

        amount_raw = request.POST.get("amount", "").strip()
        method = request.POST.get("method", "CASH").strip()
        reference = request.POST.get("reference", "").strip()
        notes = request.POST.get("notes", "").strip()

        try:
            amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Payment amount must be a valid number.")
            return self.redirect_to_detail(bill)

        if amount <= Decimal("0.00"):
            messages.error(request, "Payment amount must be greater than zero.")
            return self.redirect_to_detail(bill)

        if method not in dict(Payment.Method.choices):
            messages.error(request, "Invalid payment method.")
            return self.redirect_to_detail(bill)

        payment = Payment(
            bill=bill,
            amount=amount,
            method=method,
            reference=reference,
            notes=notes,
            received_by=request.user,
        )

        try:
            payment.full_clean()
            payment.save()
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return self.redirect_to_detail(bill)

        messages.success(
            request,
            f"Payment of ₹{amount} recorded. Balance: ₹{bill.balance}",
        )
        return self.redirect_to_detail(bill)


class InsuranceClaimAddView(BillActionMixin):
    """File a new insurance claim against a FINALIZED / PARTIAL bill."""

    def post(self, request, bill_number, *args, **kwargs):
        bill = self.get_bill(bill_number)

        if not bill.accepts_payments():
            messages.error(
                request,
                f"Insurance claims require a finalized bill (current: {bill.get_status_display()}).",
            )
            return self.redirect_to_detail(bill)

        provider = request.POST.get("provider", "").strip()
        policy_number = request.POST.get("policy_number", "").strip()
        claim_number = request.POST.get("claim_number", "").strip()
        amount_claimed_raw = request.POST.get("amount_claimed", "").strip()
        notes = request.POST.get("notes", "").strip()

        if not provider:
            messages.error(request, "Insurance provider is required.")
            return self.redirect_to_detail(bill)
        if not policy_number:
            messages.error(request, "Policy number is required.")
            return self.redirect_to_detail(bill)

        try:
            amount_claimed = Decimal(amount_claimed_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Claim amount must be a valid number.")
            return self.redirect_to_detail(bill)

        if amount_claimed <= Decimal("0.00"):
            messages.error(request, "Claim amount must be greater than zero.")
            return self.redirect_to_detail(bill)

        InsuranceClaim.objects.create(
            bill=bill,
            provider=provider,
            policy_number=policy_number,
            claim_number=claim_number,
            amount_claimed=amount_claimed,
            notes=notes,
            created_by=request.user,
        )

        messages.success(
            request,
            f"Insurance claim filed with {provider} for ₹{amount_claimed}.",
        )
        return self.redirect_to_detail(bill)
