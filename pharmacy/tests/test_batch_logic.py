from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class BatchLogicTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")
        self.category = MedicineCategory.objects.create(name="Antibiotics")
        self.supplier = Supplier.objects.create(name="ABC Pharma", phone="1234567890")
        self.store = Store.objects.create(name="Main Store", city=self.city, area=self.area)

        self.medicine = Medicine.objects.create(
            name="Amoxicillin",
            category=self.category,
            default_selling_price=Decimal("25.00"),
            gst_percentage=Decimal("5.00")
        )

        self.batch1 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="A1",
            expiry_date=timezone.now().date() + timedelta(days=30),
            purchase_price=Decimal("15"),
            selling_price=Decimal("25"),
            quantity=10
        )

        self.batch2 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="A2",
            expiry_date=timezone.now().date() + timedelta(days=60),
            purchase_price=Decimal("15"),
            selling_price=Decimal("25"),
            quantity=20
        )

    def test_cannot_create_expired_batch(self):
        with self.assertRaises(ValidationError):
            batch = Batch(
                store=self.store,
                supplier=self.supplier,
                medicine=self.medicine,
                batch_number="EX1",
                expiry_date=timezone.now().date() - timedelta(days=1),
                purchase_price=Decimal("10"),
                selling_price=Decimal("20"),
                quantity=5
            )
            batch.full_clean()

    def test_cannot_reduce_quantity_below_zero(self):
        self.batch1.quantity = -5
        with self.assertRaises(ValidationError):
            self.batch1.full_clean()

    def test_fifo_ordering(self):
        batches = Batch.objects.filter(
            store=self.store,
            medicine=self.medicine,
            expiry_date__gt=timezone.now().date(),
            quantity__gt=0
        ).order_by("expiry_date")

        self.assertEqual(batches.first().batch_number, "A1")

    def test_total_stock_calculation(self):
        total_stock = Batch.objects.filter(
            store=self.store,
            medicine=self.medicine
        ).aggregate(total=Sum("quantity"))["total"]

        self.assertEqual(total_stock, 30)
