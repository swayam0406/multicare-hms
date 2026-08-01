"""Template tags for the pharmacy app."""

from django import template
from django.core.cache import cache

from pharmacy.views import low_stock_items

register = template.Library()


_TTL_SECONDS = 60


@register.simple_tag
def low_stock_count() -> int:
    """
    Count of inventory items at or below the reorder threshold.
    Cached for 60 seconds to reduce DB load on every navbar render.
    """
    cached = cache.get("low_stock_count")
    if cached is not None:
        return cached

    value = low_stock_items().count()
    cache.set("low_stock_count", value, _TTL_SECONDS)
    return value
