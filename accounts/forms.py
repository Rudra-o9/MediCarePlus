from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, City


class BaseRegisterForm(UserCreationForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        empty_label="Select City"
    )

    class Meta:
        model = CustomUser
        fields = (
            'email',
            'full_name',
            'phone',
            'city',
            'license_number',
            'certificate',
            'password1',
            'password2',
        )


class DoctorRegisterForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = (
            'email',
            'full_name',
            'phone',
            'city',
            'license_number',
            'certificate',
            'password1',
            'password2',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'DOCTOR'
        user.is_approved = False
        if commit:
            user.save()
        return user


class PharmacistRegisterForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = (
            'email',
            'full_name',
            'phone',
            'city',
            'license_number',
            'certificate',
            'password1',
            'password2',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'PHARMACIST'
        user.is_approved = False
        if commit:
            user.save()
        return user