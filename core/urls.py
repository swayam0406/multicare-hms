from django.urls import path

from .views import AdminDashboardView, HomeView, health

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("dashboard/", AdminDashboardView.as_view(), name="dashboard"),
    path("health/", health, name="health"),
]
