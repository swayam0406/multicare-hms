"""Tests for patient views — access control, search, soft delete."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient

User = get_user_model()


class PatientAccessControlTests(TestCase):
    """Test that RBAC mixins enforce role restrictions."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin1', email='a1@test.local',
            password='pass1234', role=User.Role.ADMIN,
        )
        cls.doctor = User.objects.create_user(
            username='doc1', email='d1@test.local',
            password='pass1234', role=User.Role.DOCTOR,
        )
        cls.patient_user = User.objects.create_user(
            username='pat1', email='p1@test.local',
            password='pass1234', role=User.Role.PATIENT,
        )
        cls.patient = Patient.objects.create(
            first_name='Test',
            last_name='Patient',
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.MALE,
            phone='9876543210',
            registered_by=cls.admin,
        )

    def test_anonymous_redirected_from_list(self):
        response = self.client.get(reverse('patients:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_patient_role_forbidden_from_list(self):
        self.client.login(username='pat1', password='pass1234')
        response = self.client.get(reverse('patients:list'))
        self.assertEqual(response.status_code, 403)

    def test_doctor_allowed_on_list(self):
        self.client.login(username='doc1', password='pass1234')
        response = self.client.get(reverse('patients:list'))
        self.assertEqual(response.status_code, 200)

    def test_admin_allowed_on_list(self):
        self.client.login(username='admin1', password='pass1234')
        response = self.client.get(reverse('patients:list'))
        self.assertEqual(response.status_code, 200)

    def test_doctor_cannot_toggle_active(self):
        self.client.login(username='doc1', password='pass1234')
        url = reverse('patients:toggle_active',
                      kwargs={'patient_id': self.patient.patient_id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.is_active)  # unchanged

    def test_admin_can_toggle_active(self):
        self.client.login(username='admin1', password='pass1234')
        url = reverse('patients:toggle_active',
                      kwargs={'patient_id': self.patient.patient_id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.patient.refresh_from_db()
        self.assertFalse(self.patient.is_active)

    def test_toggle_get_returns_405(self):
        self.client.login(username='admin1', password='pass1234')
        url = reverse('patients:toggle_active',
                      kwargs={'patient_id': self.patient.patient_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_my_record_forbidden_for_staff(self):
        self.client.login(username='admin1', password='pass1234')
        response = self.client.get(reverse('patients:my_record'))
        self.assertEqual(response.status_code, 403)

    def test_my_record_404_for_unlinked_patient(self):
        self.client.login(username='pat1', password='pass1234')
        response = self.client.get(reverse('patients:my_record'))
        self.assertEqual(response.status_code, 404)

    def test_my_record_works_for_linked_patient(self):
        self.patient.user = self.patient_user
        self.patient.save()
        self.client.login(username='pat1', password='pass1234')
        response = self.client.get(reverse('patients:my_record'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Medical Record')


class PatientListSearchTests(TestCase):
    """Test list view search and filter."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin2', email='a2@test.local',
            password='pass1234', role=User.Role.ADMIN,
        )
        cls.p1 = Patient.objects.create(
            first_name='Aarav', last_name='Kumar',
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.MALE, phone='9876543210',
            registered_by=cls.admin,
        )
        cls.p2 = Patient.objects.create(
            first_name='Priya', last_name='Sharma',
            date_of_birth=date(1995, 8, 22),
            gender=Patient.Gender.FEMALE, phone='9812345678',
            registered_by=cls.admin,
        )
        cls.p3 = Patient.objects.create(
            first_name='Inactive', last_name='One',
            date_of_birth=date(1980, 1, 1),
            gender=Patient.Gender.MALE, phone='9000000000',
            is_active=False,
            registered_by=cls.admin,
        )

    def setUp(self):
        self.client.login(username='admin2', password='pass1234')

    def test_default_shows_only_active(self):
        response = self.client.get(reverse('patients:list'))
        self.assertContains(response, 'Aarav Kumar')
        self.assertContains(response, 'Priya Sharma')
        self.assertNotContains(response, 'Inactive One')

    def test_search_by_first_name(self):
        response = self.client.get(reverse('patients:list'), {'q': 'aarav'})
        self.assertContains(response, 'Aarav Kumar')
        self.assertNotContains(response, 'Priya Sharma')

    def test_search_by_phone(self):
        response = self.client.get(reverse('patients:list'), {'q': '9812'})
        self.assertContains(response, 'Priya Sharma')
        self.assertNotContains(response, 'Aarav Kumar')

    def test_search_case_insensitive(self):
        response = self.client.get(reverse('patients:list'), {'q': 'AARAV'})
        self.assertContains(response, 'Aarav Kumar')

    def test_show_inactive_filter(self):
        response = self.client.get(reverse('patients:list'), {'show': 'inactive'})
        self.assertContains(response, 'Inactive One')
        self.assertNotContains(response, 'Aarav Kumar')

    def test_show_all_filter(self):
        response = self.client.get(reverse('patients:list'), {'show': 'all'})
        self.assertContains(response, 'Aarav Kumar')
        self.assertContains(response, 'Inactive One')


class PatientCreateTests(TestCase):
    """Test the patient registration view."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin3', email='a3@test.local',
            password='pass1234', role=User.Role.ADMIN,
        )

    def setUp(self):
        self.client.login(username='admin3', password='pass1234')

    def test_register_creates_patient(self):
        response = self.client.post(reverse('patients:register'), {
            'first_name': 'New',
            'last_name': 'Patient',
            'date_of_birth': '2000-01-01',
            'gender': 'FEMALE',
            'blood_group': 'A+',
            'phone': '9876543210',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), 1)
        p = Patient.objects.first()
        self.assertEqual(p.first_name, 'New')
        self.assertEqual(p.registered_by, self.admin)

    def test_invalid_registration_shows_form(self):
        response = self.client.post(reverse('patients:register'), {
            'first_name': '',  # missing required
        })
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertEqual(Patient.objects.count(), 0)