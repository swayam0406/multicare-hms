"""Template tags for the billing app."""

from django import template

from billing.models import Bill

register = template.Library()


@register.simple_tag
def outstanding_bills_count() -> int:
    """
    Count of finalized/partial bills with balance > 0.
    Used by the navbar badge for staff users.
    Simple query — no per-bill balance recomputation needed here
    because bill.total tracks the amount owed regardless of payments.
    """
    return Bill.objects.filter(status__in=["FINALIZED", "PARTIAL"]).count()
