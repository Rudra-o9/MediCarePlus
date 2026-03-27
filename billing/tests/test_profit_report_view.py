from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class ProfitReportViewTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")
        self.admin = CustomUser.objects.create_user(
            email="admin-profit@test.com",
            password="pass123",
            role="ADMIN",
            full_name="Admin",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.doctor = CustomUser.objects.create_user(
            email="doctor-profit@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Doctor",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.pharmacist = CustomUser.objects.create_user(
            email="pharma-profit@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharmacist",
            phone="7777777777",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.patient = Patient.objects.create(
            full_name="Patient",
            age=30,
            gender="MALE",
            phone="6666666666",
            city=self.city,
            area=self.area,
            created_by=self.doctor
        )
        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )
        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="ABC Pharma", phone="1234567890")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("0.00")
        )
        Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="PR-1",
            expiry_date="2030-01-01",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=100
        )
        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="Twice daily",
            duration_days=5,
            quantity_prescribed=10
        )
        invoice = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=self.prescription_item,
            quantity=5,
            price_at_sale=Decimal("10.00")
        )
        invoice.calculate_total()
        Payment.objects.create(
            invoice=invoice,
            amount=invoice.total_amount,
            method="CASH",
            received_by=self.pharmacist
        )
        InvoiceService.process_payment(invoice, self.pharmacist)

    def test_admin_can_export_profit_report_csv(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("billing:medicine_profit_report"),
            {"export": "csv"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Medicine,Quantity Sold,Total Revenue,Total Cost,Total Profit,Profit Margin %", response.content.decode("utf-8"))
