"""Views for the doctors app."""

from django.views.generic import DetailView, ListView

from accounts.mixins import StaffRequiredMixin

from .models import Department, Doctor


class DoctorListView(StaffRequiredMixin, ListView):
    """Browse doctors by department. Staff only."""

    model = Doctor
    template_name = "doctors/doctor_list.html"
    context_object_name = "doctors"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Doctor.objects.select_related("user", "department")
            .filter(user__is_active=True)
            .order_by("department__name", "user__first_name")
        )
        dept_code = self.request.GET.get("dept", "").strip()
        if dept_code:
            qs = qs.filter(department__code=dept_code.upper())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.filter(is_active=True).order_by("name")
        ctx["selected_dept"] = self.request.GET.get("dept", "").upper()
        return ctx


class DoctorDetailView(StaffRequiredMixin, DetailView):
    """Doctor profile with availability. Staff only."""

    model = Doctor
    template_name = "doctors/doctor_detail.html"
    context_object_name = "doctor"

    def get_queryset(self):
        return Doctor.objects.select_related("user", "department").prefetch_related(
            "availabilities"
        )
