"""Forms for the accounts app."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class LoginForm(AuthenticationForm):
    """Bootstrap-styled login form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class AdminUserCreateForm(forms.ModelForm):
    """
    Admin-only form to create a new staff user.

    Not used for patient registration — patients get their user via patient
    admin flow / self-registration.
    """

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
        strip=False,
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
        strip=False,
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
        )
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "username",
                }
            ),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [(val, label) for val, label in User.Role.choices]
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"
        self.fields["is_active"].initial = True

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with that email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        elif p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
