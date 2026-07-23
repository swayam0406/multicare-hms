from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Public landing page for Multicare HMS."""
    template_name = 'core/home.html'