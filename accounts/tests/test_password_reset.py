"""Tests for password reset flow."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


class PasswordResetFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="reset_user",
            email="reset@example.com",
            password="OldPass@123",
            role=User.Role.RECEPTIONIST,
        )

    def test_reset_page_loads(self):
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset your password")

    def test_submitting_email_sends_reset_email(self):
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": "reset@example.com",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Multicare HMS", email.subject)
        self.assertIn("reset@example.com", email.to)

    def test_email_contains_reset_link(self):
        self.client.post(reverse("accounts:password_reset"), {
            "email": "reset@example.com",
        })
        body = mail.outbox[0].body
        self.assertIn("password-reset/confirm/", body)

    def test_unknown_email_does_not_send_but_still_succeeds(self):
        """Security: don't reveal whether an account exists."""
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": "nonexistent@example.com",
        })
        # Still redirects to "done" page
        self.assertEqual(response.status_code, 302)
        # But no email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_done_page_loads(self):
        response = self.client.get(reverse("accounts:password_reset_done"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check your email")

    def test_valid_token_shows_password_form(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # Django's confirm view redirects to a "set-password" internal URL —
        # follow the redirect
        url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": uidb64, "token": token,
        })
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set a new password")

    def test_invalid_token_shows_error(self):
        url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": "abc", "token": "invalid-token",
        })
        response = self.client.get(url, follow=True)
        self.assertContains(response, "Reset link is invalid")

    def test_setting_new_password_works(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # First GET establishes the token in the session
        confirm_url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": uidb64, "token": token,
        })
        self.client.get(confirm_url, follow=True)

        # Then POST to the internal set-password URL
        set_url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": uidb64, "token": "set-password",
        })
        response = self.client.post(set_url, {
            "new_password1": "NewStrongPass@2026",
            "new_password2": "NewStrongPass@2026",
        })
        self.assertEqual(response.status_code, 302)

        # Old password no longer works
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("OldPass@123"))
        self.assertTrue(self.user.check_password("NewStrongPass@2026"))

    def test_password_mismatch_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        confirm_url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": uidb64, "token": token,
        })
        self.client.get(confirm_url, follow=True)

        set_url = reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": uidb64, "token": "set-password",
        })
        response = self.client.post(set_url, {
            "new_password1": "NewStrongPass@2026",
            "new_password2": "DifferentPass@2026",
        })
        # Form re-renders with errors, no redirect
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass@123"))

    def test_complete_page_loads(self):
        response = self.client.get(reverse("accounts:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password reset complete")
