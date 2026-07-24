from django.apps import AppConfig


class MedicalRecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "medical_records"
    verbose_name = "Medical Records"

    def ready(self):
        # Import signals so they get connected on app startup
        from . import signals  # noqa: F401
