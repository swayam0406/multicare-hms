"""URL configuration for the pharmacy app."""

from django.urls import path

from .views import (
    DispenseCreateView,
    DispenseDetailView,
    InventoryAdjustView,
    InventoryListView,
    InventoryMovementsView,
    InventoryReceiveView,
    PharmacyQueueView,
)

app_name = "pharmacy"

urlpatterns = [
    # T-7.9 — queue + dispense
    path("queue/", PharmacyQueueView.as_view(), name="queue"),
    path(
        "prescriptions/<int:prescription_pk>/dispense/",
        DispenseCreateView.as_view(),
        name="dispense_create",
    ),
    path("dispenses/<int:pk>/", DispenseDetailView.as_view(), name="dispense_detail"),
    # T-7.10 — inventory
    path("inventory/", InventoryListView.as_view(), name="inventory_list"),
    path("inventory/<int:pk>/receive/", InventoryReceiveView.as_view(), name="inventory_receive"),
    path("inventory/<int:pk>/adjust/", InventoryAdjustView.as_view(), name="inventory_adjust"),
    path(
        "inventory/<int:pk>/movements/",
        InventoryMovementsView.as_view(),
        name="inventory_movements",
    ),
]
