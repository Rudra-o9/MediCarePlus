from django import forms
from .models import Patient


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'full_name',
            'age',
            'gender',
            'phone',
            'city',
            'area',
            'address',
            'medical_history',
        ]
