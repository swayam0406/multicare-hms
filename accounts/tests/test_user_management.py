"""Tests for admin user creation + user list views."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserListAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="ul_admin",
            email="uladmin@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        cls.doc = User.objects.create_user(
            username="ul_doc",
            email="uldoc@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )
        cls.pat = User.objects.create_user(
            username="ul_pat",
            email="ulpat@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )

    def test_admin_can_access_list(self):
        self.client.login(username="ul_admin", password="pass1234")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)

    def test_doctor_forbidden(self):
        self.client.login(username="ul_doc", password="pass1234")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_patient_forbidden(self):
        self.client.login(username="ul_pat", password="pass1234")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 302)


class UserListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="lf_admin",
            email="lfa@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        User.objects.create_user(
            username="alice_doc",
            email="ad@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
            first_name="Alice",
            last_name="Doctor",
        )
        User.objects.create_user(
            username="bob_nurse",
            email="bn@t.local",
            password="pass1234",
            role=User.Role.NURSE,
            first_name="Bob",
            last_name="Nurse",
        )
        User.objects.create_user(
            username="carol_recep",
            email="cr@t.local",
            password="pass1234",
            role=User.Role.RECEPTIONIST,
            first_name="Carol",
            last_name="Recep",
        )

    def test_search_by_username(self):
        self.client.login(username="lf_admin", password="pass1234")
        response = self.client.get(reverse("accounts:user_list") + "?q=alice")
        self.assertContains(response, "alice_doc")
        self.assertNotContains(response, "bob_nurse")

    def test_search_by_first_name(self):
        self.client.login(username="lf_admin", password="pass1234")
        response = self.client.get(reverse("accounts:user_list") + "?q=Bob")
        self.assertContains(response, "bob_nurse")
        self.assertNotContains(response, "alice_doc")

    def test_role_filter(self):
        self.client.login(username="lf_admin", password="pass1234")
        response = self.client.get(reverse("accounts:user_list") + "?role=NURSE")
        self.assertContains(response, "bob_nurse")
        self.assertNotContains(response, "alice_doc")
        self.assertNotContains(response, "carol_recep")


class UserCreateAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="uc_admin",
            email="uca@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        cls.doc = User.objects.create_user(
            username="uc_doc",
            email="ucd@t.local",
            password="pass1234",
            role=User.Role.DOCTOR,
        )

    def test_admin_can_view_form(self):
        self.client.login(username="uc_admin", password="pass1234")
        response = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(response.status_code, 200)

    def test_doctor_forbidden(self):
        self.client.login(username="uc_doc", password="pass1234")
        response = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(response.status_code, 403)


class UserCreateFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="cf_admin",
            email="cfa@t.local",
            password="pass1234",
            role=User.Role.ADMIN,
        )

    def test_valid_submission_creates_user(self):
        self.client.login(username="cf_admin", password="pass1234")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "newnurse",
                "email": "nn@t.local",
                "first_name": "New",
                "last_name": "Nurse",
                "role": "NURSE",
                "is_active": "on",
                "password1": "StrongPass@2026",
                "password2": "StrongPass@2026",
            },
        )
        self.assertEqual(response.status_code, 302)

        u = User.objects.get(username="newnurse")
        self.assertEqual(u.role, "NURSE")
        self.assertTrue(u.check_password("StrongPass@2026"))
        self.assertTrue(u.is_active)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(
            username="taken",
            email="t@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        self.client.login(username="cf_admin", password="pass1234")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "taken",
                "email": "other@t.local",
                "first_name": "X",
                "last_name": "Y",
                "role": "NURSE",
                "is_active": "on",
                "password1": "StrongPass@2026",
                "password2": "StrongPass@2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="original",
            email="dup@t.local",
            password="pass1234",
            role=User.Role.PATIENT,
        )
        self.client.login(username="cf_admin", password="pass1234")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "newuser",
                "email": "dup@t.local",
                "first_name": "X",
                "last_name": "Y",
                "role": "NURSE",
                "is_active": "on",
                "password1": "StrongPass@2026",
                "password2": "StrongPass@2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_password_mismatch_rejected(self):
        self.client.login(username="cf_admin", password="pass1234")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "pw",
                "email": "pw@t.local",
                "first_name": "X",
                "last_name": "Y",
                "role": "NURSE",
                "is_active": "on",
                "password1": "StrongPass@2026",
                "password2": "DifferentPass@2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "do not match")
        self.assertFalse(User.objects.filter(username="pw").exists())

    def test_weak_password_rejected(self):
        self.client.login(username="cf_admin", password="pass1234")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "weak",
                "email": "weak@t.local",
                "first_name": "X",
                "last_name": "Y",
                "role": "NURSE",
                "is_active": "on",
                "password1": "1234",
                "password2": "1234",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="weak").exists())

    def test_welcome_email_sent(self):
        from django.core import mail

        self.client.login(username="cf_admin", password="pass1234")
        self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "greetme",
                "email": "greet@t.local",
                "first_name": "Greet",
                "last_name": "Me",
                "role": "NURSE",
                "is_active": "on",
                "password1": "StrongPass@2026",
                "password2": "StrongPass@2026",
            },
        )
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("greet@t.local", mail.outbox[-1].to)
