"""Template tags for the pharmacy app."""

from django import template

from pharmacy.views import low_stock_items

register = template.Library()


@register.simple_tag
def low_stock_count() -> int:
    """Count of inventory items at or below the reorder threshold."""
    return low_stock_items().count()
