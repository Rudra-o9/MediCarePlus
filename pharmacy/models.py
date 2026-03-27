"""Inventory and store-side models for MediCarePlus.

Feature ownership:
- medicine/category define the catalog,
- supplier and store support procurement and fulfillment,
- batch stores expiry-aware stock,
- stock movement is the audit trail for purchases, sales, returns, and adjustments.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from accounts.models import Area, City

class MedicineCategory(models.Model):
    """Medicine classification used for reporting and organization."""
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class Supplier(models.Model):
    """Vendor from whom the admin buys stock in bulk."""
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Store(models.Model):
    """A real pharmacy/store location.

    Important real-world rule:
    stock belongs to a store, not to an individual pharmacist.
    """
    name = models.CharField(max_length=255)
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="stores"
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        related_name="stores",
        null=True,
        blank=True
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="stores",
        blank=True,
        limit_choices_to={"role": "PHARMACIST"}
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["city__name", "name"]
        unique_together = ("city", "name")

    def __str__(self):
        return f"{self.name} ({self.city.name})"

class Medicine(models.Model):
    """Medicine master data used across prescription, inventory, and billing."""
    name = models.CharField(max_length=255, unique=True)
    manufacturer = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    default_selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Default selling price per unit"
    )

    # 🔵 NEW FIELD
    gst_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Total GST percentage (will be split into CGST + SGST)"
    )

    category = models.ForeignKey(
        MedicineCategory,
        on_delete=models.PROTECT,
        related_name="medicines"
    )

    hsn_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="HSN code for GST reporting"
    )

    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=10)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    def __str__(self):
        return f"{self.name} ({self.stock_quantity} in stock)"

class Batch(models.Model):
    """Expiry-aware stock unit purchased for a specific store."""
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="batches",
        null=True,
        blank=True,
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="batches",
    ) 
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name="batches")
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)   

    class Meta:
        ordering = ["expiry_date"]
        unique_together = ("store", "medicine", "batch_number")

    def __str__(self):
        store_name = self.store.name if self.store else "Unassigned Store"
        return f"{self.medicine.name} - {self.batch_number} @ {store_name} ({self.quantity})"

    def save(self, *args, **kwargs):
        # Keep medicine-level stock in sync with store batches and create audit
        # entries whenever a batch is first purchased or manually adjusted.
        is_new = self.pk is None
        old_quantity = 0

        if not is_new:
            old_batch = Batch.objects.get(pk=self.pk)
            old_quantity = old_batch.quantity

        self.full_clean()
        super().save(*args, **kwargs)

        quantity_difference = self.quantity - old_quantity

        if is_new:
            # Log purchase
            StockMovement.objects.create(
                medicine=self.medicine,
                batch=self,
                movement_type="PURCHASE",
                quantity=self.quantity,
                reference=f"Batch {self.batch_number}"
            )
        elif quantity_difference != 0:
            # Log adjustment
            StockMovement.objects.create(
                medicine=self.medicine,
                batch=self,
                movement_type="ADJUSTMENT",
                quantity=quantity_difference,
                reference=f"Batch Update {self.batch_number}"
            )

        self.update_medicine_stock()

    def delete(self, *args, **kwargs):
        medicine = self.medicine
        super().delete(*args, **kwargs)
        total = medicine.batches.aggregate(total=Sum("quantity"))["total"] or 0
        medicine.stock_quantity = total
        medicine.save(update_fields=["stock_quantity"])

    def clean(self):
        """Protect against invalid expiry dates and location mismatches."""
        if self.expiry_date and self.expiry_date <= timezone.now().date():
            raise ValidationError("Cannot create batch with past expiry date.")
        if self.quantity <= 0:
            raise ValidationError("Batch quantity must be greater than zero.")
        if self.purchase_price <= 0:
            raise ValidationError("Purchase price must be greater than zero.")
        if self.selling_price <= 0:
            raise ValidationError("Selling price must be greater than zero.")
        if self.area_mismatch():
            raise ValidationError("Selected store area does not belong to the selected city.")

    def area_mismatch(self):
        return bool(self.store and self.store.area and self.store.area.city_id != self.store.city_id)

    def update_medicine_stock(self):
        total = self.medicine.batches.aggregate(total=Sum("quantity"))["total"] or 0
        self.medicine.stock_quantity = total
        self.medicine.save(update_fields=["stock_quantity"])

    def is_near_expiry(self, days=30):
        from django.utils import timezone
        today = timezone.now().date()
        return today <= self.expiry_date <= today + timezone.timedelta(days=days)

    def is_expired(self):
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()
    
class StockMovement(models.Model):
    """Inventory ledger entry for procurement, sale, return, or adjustment."""

    MOVEMENT_TYPES = (
        ("PURCHASE", "Purchase"),
        ("SALE", "Sale"),
        ("ADJUSTMENT", "Adjustment"),
        ("RETURN", "Return"),
    )

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name="stock_movements"
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements"
    )

    batch = models.ForeignKey(
        Batch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements"
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPES
    )

    quantity = models.IntegerField(
        help_text="Positive for incoming, negative for outgoing"
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Invoice number or manual reference"
    )

    performed_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        store_name = self.store.name if self.store else "No Store"
        return f"{self.medicine.name} | {store_name} | {self.movement_type} | {self.quantity}"
    
