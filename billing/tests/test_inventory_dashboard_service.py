from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.services.inventory_dashboard_service import InventoryDashboardService
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class InventoryDashboardServiceTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Mumbai", state="Maharashtra", country="India")
        self.area = Area.objects.create(city=self.city, name="Andheri")

        self.user = CustomUser.objects.create_user(
            email="admin@test.com",
            password="pass123",
            role="ADMIN",
            full_name="Admin",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.store = Store.objects.create(name="Admin Store", city=self.city, area=self.area)
        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier", phone="1234567890")

        self.medicine1 = Medicine.objects.create(
            name="MedA",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("5.00")
        )

        self.medicine2 = Medicine.objects.create(
            name="MedB",
            category=self.category,
            default_selling_price=Decimal("20.00"),
            gst_percentage=Decimal("5.00")
        )

        today = timezone.now().date()

        Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine1,
            batch_number="A1",
            expiry_date=today + timedelta(days=5),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=5
        )

        expired_batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine2,
            batch_number="B1",
            expiry_date=today + timedelta(days=5),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("20.00"),
            quantity=8
        )

        Batch.objects.filter(pk=expired_batch.pk).update(expiry_date=today - timedelta(days=5))

    def test_dashboard_summary_structure(self):
        result = InventoryDashboardService.get_summary()

        self.assertIn("near_expiry_count", result)
        self.assertIn("expired_count", result)
        self.assertIn("dead_stock_count", result)
        self.assertIn("low_stock_count", result)

    def test_dashboard_counts_are_correct(self):
        result = InventoryDashboardService.get_summary(
            days_near_expiry=30,
            dead_stock_days=60,
            low_stock_threshold=10
        )

        self.assertEqual(result["near_expiry_count"], 1)
        self.assertEqual(result["expired_count"], 1)
        self.assertEqual(result["dead_stock_count"], 2)
        self.assertEqual(result["low_stock_count"], 2)
