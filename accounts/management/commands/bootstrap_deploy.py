"""
One-shot deploy bootstrap: ensures an admin user exists and all catalogs are
seeded. Idempotent — safe to run on every container start.

Reads:
  - DJANGO_ADMIN_USERNAME (default: 'admin')
  - DJANGO_ADMIN_EMAIL    (default: 'admin@multicare.local')
  - DJANGO_ADMIN_PASSWORD (required — no default)

Called from entrypoint.sh in production.
"""

import os

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
        # Ensure role/flags are correct even if user existed before
        user.role = "ADMIN"
        user.is_staff = True
        user.is_superuser = True
        user.email = email
        user.set_password(password)
        user.save()

        state = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' {state} (role=ADMIN)."))

    def _run_seeds(self):
        """Run seed commands; skip silently if a command doesn't exist."""
        for seed_cmd in ["seed_services", "seed_lab_tests", "seed_catalogs"]:
            try:
                self.stdout.write(f"Running {seed_cmd}...")
                call_command(seed_cmd)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Skipped {seed_cmd}: {exc}"))
