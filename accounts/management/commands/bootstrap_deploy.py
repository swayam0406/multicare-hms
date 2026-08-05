import os
import traceback

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Bootstrap admin user and seed catalog data (idempotent)."

    def handle(self, *args, **options):
        self._ensure_admin()
        self._run_seeds()
        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))

    def _ensure_admin(self):
        User = get_user_model()
        username = os.environ.get("DJANGO_ADMIN_USERNAME", "admin")
        email = os.environ.get("DJANGO_ADMIN_EMAIL", "admin@multicare.local")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")

        if not password:
            self.stdout.write(
                self.style.WARNING("DJANGO_ADMIN_PASSWORD not set; skipping admin creation.")
            )
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": "ADMIN",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.role = "ADMIN"
        user.is_staff = True
        user.is_superuser = True
        user.email = email
        user.set_password(password)
        user.save()

        state = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' {state} (role=ADMIN)."))

    def _run_seeds(self):
        """Run seeds. Catalog seeds skip silently; demo seed prints traceback."""
        catalog_seeds = ["seed_services", "seed_lab_tests", "seed_catalogs"]
        for seed_cmd in catalog_seeds:
            try:
                self.stdout.write(f"Running {seed_cmd}...")
                call_command(seed_cmd)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Skipped {seed_cmd}: {exc}"))

        # Demo seed — log full traceback if it fails, so we can debug
        self.stdout.write("Running seed_demo_data...")
        try:
            call_command("seed_demo_data")
            self.stdout.write(self.style.SUCCESS("  seed_demo_data completed successfully."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  seed_demo_data FAILED: {exc}"))
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
