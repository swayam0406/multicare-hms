"""Tests for the PatientForm."""

from datetime import date, timedelta

from django.test import TestCase

from patients.forms import PatientForm


class PatientFormTests(TestCase):
    """Test PatientForm validation and cleaning."""

    def _valid_data(self, **overrides):
        data = {
            'first_name': 'aarav',
            'last_name': 'kumar',
            'date_of_birth': '1990-05-15',
            'gender': 'MALE',
            'blood_group': 'O+',
            'phone': '9876543210',
        }
        data.update(overrides)
        return data

    def test_valid_form_passes(self):
        form = PatientForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_first_name_title_cased(self):
        form = PatientForm(data=self._valid_data(first_name='aarav'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['first_name'], 'Aarav')

    def test_last_name_title_cased(self):
        form = PatientForm(data=self._valid_data(last_name='kumar'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['last_name'], 'Kumar')

    def test_future_dob_rejected(self):
        future = (date.today() + timedelta(days=10)).isoformat()
        form = PatientForm(data=self._valid_data(date_of_birth=future))
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)

    def test_unrealistic_age_rejected(self):
        form = PatientForm(data=self._valid_data(date_of_birth='1850-01-01'))
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)

    def test_invalid_phone_rejected(self):
        form = PatientForm(data=self._valid_data(phone='123'))
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_missing_required_field(self):
        data = self._valid_data()
        del data['first_name']
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)

    def test_emergency_contact_name_without_phone_rejected(self):
        form = PatientForm(data=self._valid_data(
            emergency_contact_name='Rita Kumar',
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('emergency_contact_phone', form.errors)

    def test_emergency_contact_phone_without_name_rejected(self):
        form = PatientForm(data=self._valid_data(
            emergency_contact_phone='9812345678',
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('emergency_contact_name', form.errors)

    def test_emergency_contact_both_provided_valid(self):
        form = PatientForm(data=self._valid_data(
            emergency_contact_name='Rita Kumar',
            emergency_contact_phone='9812345678',
        ))
        self.assertTrue(form.is_valid(), msg=form.errors)