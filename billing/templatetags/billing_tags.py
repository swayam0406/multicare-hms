"""Template tags for the billing app."""

from django import template
from django.core.cache import cache

register = template.Library()


# 60-second TTL. Short enough to feel live; long enough to save DB hits.
_TTL_SECONDS = 60


@register.simple_tag
def outstanding_bills_count() -> int:
    """
    Count of bills that are FINALIZED or PARTIAL (i.e., have outstanding balance).
    Cached for 60 seconds to reduce DB load on every navbar render.
    """
    cached = cache.get("outstanding_bills_count")
    if cached is not None:
        return cached

    from billing.models import Bill

    value = Bill.objects.filter(status__in=["FINALIZED", "PARTIAL"]).count()
    cache.set("outstanding_bills_count", value, _TTL_SECONDS)
    return value
