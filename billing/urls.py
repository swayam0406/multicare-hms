"""URL configuration for the billing app."""

from django.urls import path

from .views import (
    BillDetailView,
    BillFinalizeView,
    BillItemAddView,
    BillItemDeleteView,
    BillListView,
    InsuranceClaimAddView,
    PaymentAddView,
)

app_name = "billing"

urlpatterns = [
    path("", BillListView.as_view(), name="list"),
    path("<str:bill_number>/", BillDetailView.as_view(), name="detail"),
    path("<str:bill_number>/items/add/", BillItemAddView.as_view(), name="item_add"),
    path(
        "<str:bill_number>/items/<int:item_pk>/delete/",
        BillItemDeleteView.as_view(),
        name="item_delete",
    ),
    path("<str:bill_number>/finalize/", BillFinalizeView.as_view(), name="finalize"),
    path("<str:bill_number>/payments/add/", PaymentAddView.as_view(), name="payment_add"),
    path("<str:bill_number>/insurance/add/", InsuranceClaimAddView.as_view(), name="insurance_add"),
]
