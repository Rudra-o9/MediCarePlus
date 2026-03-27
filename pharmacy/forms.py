"""Pharmacy master-data forms used in the app UI."""

from django import forms

from .models import Medicine, MedicineCategory, Supplier


class MedicineCategoryForm(forms.ModelForm):
    """Create or update medicine categories."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "No parent category"
        self.fields["parent"].queryset = MedicineCategory.objects.order_by("name")

        if self.instance and self.instance.pk:
            self.fields["parent"].queryset = self.fields["parent"].queryset.exclude(pk=self.instance.pk)

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if self.instance and self.instance.pk and parent and parent.pk == self.instance.pk:
            raise forms.ValidationError("A category cannot be its own parent.")
        return parent

    class Meta:
        model = MedicineCategory
        fields = ["name", "description", "parent"]


class SupplierForm(forms.ModelForm):
    """Create or update supplier master data."""

    class Meta:
        model = Supplier
        fields = [
            "name",
            "contact_person",
            "phone",
            "email",
            "gst_number",
            "address",
            "is_active",
        ]


class MedicineForm(forms.ModelForm):
    """Create or update medicine master data and pricing."""

    class Meta:
        model = Medicine
        fields = [
            "name",
            "manufacturer",
            "description",
            "default_selling_price",
            "gst_percentage",
            "category",
            "hsn_code",
            "low_stock_threshold",
            "is_active",
        ]
