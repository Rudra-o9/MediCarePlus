from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.services.inventory_service import InventoryService
from pharmacy.models import Batch, Medicine, MedicineCategory, StockMovement, Store, Supplier


class InventoryServiceTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.user = CustomUser.objects.create_user(
            email="pharma@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.store = Store.objects.create(name="Store 1", city=self.city, area=self.area)
        self.store.staff.add(self.user)
        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier", phone="1234567890")

        self.medicine1 = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("5.00")
        )

        self.medicine2 = Medicine.objects.create(
            name="Ibuprofen",
            category=self.category,
            default_selling_price=Decimal("20.00"),
            gst_percentage=Decimal("5.00")
        )

        today = timezone.now().date()

        self.near_batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine1,
            batch_number="N1",
            expiry_date=today + timedelta(days=10),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.far_batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine1,
            batch_number="F1",
            expiry_date=today + timedelta(days=120),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.expired_batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine2,
            batch_number="E1",
            expiry_date=today + timedelta(days=5),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("20.00"),
            quantity=15
        )

        Batch.objects.filter(pk=self.expired_batch.pk).update(expiry_date=today - timedelta(days=5))
        self.expired_batch.refresh_from_db()

    def test_near_expiry_batches(self):
        result = InventoryService.near_expiry_batches(days=30)

        self.assertIn(self.near_batch, result)
        self.assertNotIn(self.far_batch, result)
        self.assertNotIn(self.expired_batch, result)

    def test_near_expiry_respects_quantity(self):
        self.near_batch.quantity = 0
        self.near_batch.save(update_fields=["quantity"])

        result = InventoryService.near_expiry_batches(days=30)

        self.assertNotIn(self.near_batch, result)

    def test_expired_batches(self):
        result = InventoryService.expired_batches()

        self.assertIn(self.expired_batch, result)
        self.assertNotIn(self.near_batch, result)
        self.assertNotIn(self.far_batch, result)

    def test_expired_batches_respects_quantity(self):
        Batch.objects.filter(pk=self.expired_batch.pk).update(quantity=0)
        self.expired_batch.refresh_from_db()

        result = InventoryService.expired_batches()

        self.assertNotIn(self.expired_batch, result)

    def test_dead_stock_detects_unsold_medicines(self):
        StockMovement.objects.create(
            medicine=self.medicine1,
            store=self.store,
            batch=self.near_batch,
            movement_type="SALE",
            quantity=-2
        )

        result = InventoryService.dead_stock(days_without_sale=60)

        self.assertNotIn(self.medicine1, result)
        self.assertIn(self.medicine2, result)

    def test_dead_stock_all_if_no_sales(self):
        result = InventoryService.dead_stock(days_without_sale=60)

        self.assertIn(self.medicine1, result)
        self.assertIn(self.medicine2, result)
