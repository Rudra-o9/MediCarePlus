"""Forms for registration and admin operational workflows.

This file is useful when explaining:
- how doctors/pharmacists register,
- how stores are created,
- how pharmacists are assigned to stores,
- how batch procurement data is captured from the admin UI.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db.models import F, Q
from pharmacy.models import Batch, Store
from .models import Area, CustomUser, City, SystemSetting


class BaseRegisterForm(UserCreationForm):
    """Shared registration structure for role-based user onboarding."""
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
            'area',
            'license_number',
            'certificate',
            'password1',
            'password2',
        )


class DoctorRegisterForm(UserCreationForm):
    """Doctor registration form.

    The role is forced in `save()` so a user cannot self-register as another role.
    """
    class Meta:
        model = CustomUser
        fields = (
            'email',
            'full_name',
            'phone',
            'city',
            'area',
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
    """Pharmacist registration form with forced PHARMACIST role."""
    class Meta:
        model = CustomUser
        fields = (
            'email',
            'full_name',
            'phone',
            'city',
            'area',
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


class StoreForm(forms.ModelForm):
    """Admin form for creating and maintaining pharmacy stores."""
    city = forms.ModelChoiceField(
        queryset=City.objects.filter(is_active=True).order_by("name"),
        empty_label="Select City"
    )
    area = forms.ModelChoiceField(
        queryset=Area.objects.filter(is_active=True).select_related("city").order_by("city__name", "name"),
        required=False,
        empty_label="Select Area"
    )

    class Meta:
        model = Store
        fields = ["name", "city", "area", "address", "phone", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        city = None
        if self.is_bound:
            city_key = self.add_prefix("city")
            city_value = self.data.get(city_key)
            if city_value:
                try:
                    city = City.objects.get(pk=city_value, is_active=True)
                except City.DoesNotExist:
                    city = None
        elif self.instance and self.instance.pk and self.instance.city_id:
            city = self.instance.city

        self.fields["area"].queryset = Area.objects.filter(
            is_active=True
        ).select_related("city").order_by("city__name", "name")

        area_choices = [("", self.fields["area"].empty_label or "Select Area")]
        for area in self.fields["area"].queryset:
            area_choices.append((str(area.pk), area.name))
        self.fields["area"].choices = area_choices

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get("city")
        area = cleaned_data.get("area")
        if area and city and area.city_id != city.id:
            self.add_error("area", "Selected area does not belong to the selected city.")
        return cleaned_data


class StoreStaffAssignmentForm(forms.Form):
    """Assign an approved pharmacist to a store from the admin operations page."""
    pharmacist = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        empty_label="Select Pharmacist"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pharmacist"].queryset = CustomUser.objects.filter(
            role="PHARMACIST",
            is_approved=True
        ).order_by("full_name")
        self.fields["pharmacist"].label_from_instance = lambda user: f"{user.full_name} ({user.email})"


class BatchProcurementForm(forms.ModelForm):
    """Admin form for recording newly purchased stock batches."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["store"].queryset = Store.objects.filter(
            Q(area__isnull=True) | Q(area__city_id=F("city_id"))
        ).select_related("city", "area").order_by("name")
        self.fields["store"].label_from_instance = lambda store: f"{store.name} ({store.city.name})"

    def clean(self):
        cleaned_data = super().clean()
        store = cleaned_data.get("store")
        medicine = cleaned_data.get("medicine")
        batch_number = cleaned_data.get("batch_number")

        if store and medicine and batch_number:
            duplicate_exists = Batch.objects.filter(
                store=store,
                medicine=medicine,
                batch_number=batch_number,
            ).exists()
            if duplicate_exists:
                self.add_error(
                    "batch_number",
                    "This batch number already exists for the selected store and medicine.",
                )

        return cleaned_data

    class Meta:
        model = Batch
        fields = [
            "store",
            "supplier",
            "medicine",
            "batch_number",
            "expiry_date",
            "purchase_price",
            "selling_price",
            "quantity",
        ]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }


class SystemSettingForm(forms.ModelForm):
    """Admin form for runtime security and onboarding settings."""

    class Meta:
        model = SystemSetting
        fields = [
            "allow_doctor_self_registration",
            "allow_pharmacist_self_registration",
            "doctor_approval_required",
            "pharmacist_approval_required",
            "expiry_alert_days",
        ]
