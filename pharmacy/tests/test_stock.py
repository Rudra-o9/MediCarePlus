from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from pharmacy.models import Batch, Medicine, MedicineCategory, StockMovement, Store, Supplier


class InventoryReportViewTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Ahmedabad", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Navrangpura")

        self.admin = CustomUser.objects.create_user(
            email="admin@test.com",
            password="pass123",
            role="ADMIN",
            full_name="Admin User",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True,
        )
        self.pharmacist = CustomUser.objects.create_user(
            email="pharma@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma User",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True,
        )
        self.doctor = CustomUser.objects.create_user(
            email="doctor@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Doctor User",
            phone="7777777777",
            city=self.city,
            area=self.area,
            is_approved=True,
        )

        self.store = Store.objects.create(name="Main Store", city=self.city, area=self.area, is_active=True)
        self.store.staff.add(self.pharmacist)
        self.category = MedicineCategory.objects.create(name="Antibiotics")
        self.supplier = Supplier.objects.create(name="ABC Supplier", phone="9999999998")
        self.medicine = Medicine.objects.create(
            name="Amoxicillin",
            category=self.category,
            default_selling_price=Decimal("25.00"),
            gst_percentage=Decimal("5.00"),
            stock_quantity=12,
            low_stock_threshold=10,
            is_active=True,
        )
        Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="AMX-1",
            expiry_date=timezone.localdate() + timedelta(days=10),
            purchase_price=Decimal("10.00"),
            selling_price=Decimal("25.00"),
            quantity=12,
        )

    def test_stock_report_renders_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("stock_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock Position by Medicine")
        self.assertContains(response, "Amoxicillin")

    def test_medicine_list_renders_for_pharmacist(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("medicine_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Medicine Directory")
        self.assertContains(response, "Amoxicillin")

    def test_low_stock_renders_for_pharmacist(self):
        self.medicine.stock_quantity = 8
        self.medicine.save(update_fields=["stock_quantity"])
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("low_stock_medicines"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Stock Medicines")
        self.assertContains(response, "8")

    def test_doctor_medicine_stock_renders_for_doctor(self):
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("doctor_medicine_stock"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Medicine Availability Snapshot")
        self.assertContains(response, "Amoxicillin")

    def test_category_sales_report_shows_positive_sales_metrics(self):
        StockMovement.objects.create(
            medicine=self.medicine,
            store=self.store,
            batch=self.medicine.batches.first(),
            movement_type="SALE",
            quantity=-3,
            reference="INV-TEST-1",
            performed_by=self.pharmacist,
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse("category_sales_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Category Sales Breakdown")
        self.assertContains(response, "3")
        self.assertNotContains(response, "-3")
        self.assertContains(response, "Rs. 75.00")
