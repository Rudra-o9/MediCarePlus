from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, InvoiceItemBatch, Payment
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class InvoiceListViewTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = CustomUser.objects.create_user(
            email="doc-view@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Doc View",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True,
        )
        self.pharmacist = CustomUser.objects.create_user(
            email="pharma-view@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma View",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True,
        )

        self.patient = Patient.objects.create(
            full_name="Invoice Patient",
            age=30,
            gender="MALE",
            phone="7777777777",
            city=self.city,
            area=self.area,
            created_by=self.doctor,
        )
        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)
        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier View", phone="1234567890")
        self.medicine = Medicine.objects.create(
            name="Invoice Medicine",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("0.00"),
        )
        self.batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="INV-1",
            expiry_date=timezone.localdate() + timedelta(days=30),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=20,
        )

        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT",
        )
        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="2 times daily",
            duration_days=5,
            quantity_prescribed=4,
        )

        self.invoice = Invoice.objects.create(prescription=self.prescription)
        self.invoice_item = InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=2,
            price_at_sale=Decimal("10.00"),
        )
        InvoiceItemBatch.objects.create(
            invoice_item=self.invoice_item,
            batch=self.batch,
            quantity=2,
        )
        self.invoice.calculate_total()
        Payment.objects.create(
            invoice=self.invoice,
            amount=self.invoice.total_amount,
            method="CASH",
            received_by=self.pharmacist,
        )
        self.invoice.status = "PAID"
        self.invoice.save(update_fields=["status"])

    def test_invoice_list_renders_for_pharmacist(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:invoice_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoice Queue")
        self.assertContains(response, "Invoice Patient")
        self.assertContains(response, "Paid")

    def test_invoice_detail_renders_new_workspace(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:invoice_detail", args=[self.invoice.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoice Detail Workspace")
        self.assertContains(response, self.invoice.invoice_number)
        self.assertContains(response, "Billing Snapshot")
        self.assertContains(response, "Batch INV-1 x 2")

    def test_prescription_queue_renders_for_pharmacist(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:prescription_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prescription")

    def test_sales_report_renders_for_pharmacist(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:sales_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sales Report")
        self.assertContains(response, "Prescriptions")
        self.assertContains(response, "Invoices")

    def test_sales_report_explains_missing_store_assignment(self):
        self.store.staff.remove(self.pharmacist)
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:sales_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No active store is assigned to this pharmacist account.")

    def test_invoice_detail_sidebar_includes_inventory_navigation(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:invoice_detail", args=[self.invoice.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Stock")
        self.assertContains(response, "Sales Report")

    def test_prescription_queue_explains_missing_store_assignment(self):
        self.store.staff.remove(self.pharmacist)
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:prescription_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No active store is assigned to this pharmacist account.")

    def test_invoice_list_explains_missing_store_assignment(self):
        self.store.staff.remove(self.pharmacist)
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("billing:invoice_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No active store is assigned to this pharmacist account.")
