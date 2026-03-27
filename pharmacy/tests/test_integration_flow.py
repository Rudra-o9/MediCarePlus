from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class FullSystemIntegrationTest(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Surat", state="GJ", country="IN")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = CustomUser.objects.create_user(
            email="doc@test.com",
            password="123456",
            full_name="Dr Test",
            phone="9999999999",
            role="DOCTOR",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.pharmacist = CustomUser.objects.create_user(
            email="pharma@test.com",
            password="123456",
            full_name="Pharma Test",
            phone="8888888888",
            role="PHARMACIST",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.patient = Patient.objects.create(
            full_name="John Doe",
            age=30,
            gender="MALE",
            phone="7777777777",
            city=self.city,
            area=self.area,
            created_by=self.doctor
        )

        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.store = Store.objects.create(name="Local Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )

        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="ABC Pharma", phone="1111111111")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("0.00"),
            stock_quantity=0,
            is_active=True
        )

        self.batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B001",
            expiry_date="2030-12-31",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=100
        )

        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="2 times daily",
            duration_days=5,
            quantity_prescribed=10
        )

        self.invoice = Invoice.objects.create(prescription=self.prescription)

        self.invoice_item = InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=5,
            price_at_sale=Decimal("10.00")
        )

    def test_invoice_total_calculation(self):
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("50.00"))

        InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=3,
            price_at_sale=Decimal("10.00")
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("80.00"))

    def test_batch_stock_update(self):
        self.assertEqual(self.medicine.stock_quantity, 100)

        self.batch.quantity = 60
        self.batch.save()
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.stock_quantity, 60)

    def test_prescription_item_dispense_limit(self):
        with self.assertRaises(ValidationError):
            InvoiceItem.objects.create(
                invoice=self.invoice,
                prescription_item=self.prescription_item,
                quantity=20,
                price_at_sale=Decimal("10.00")
            )

    def test_invoice_item_modification_lock(self):
        self.invoice.status = "PAID"
        self.invoice.save()

        self.invoice_item.quantity = 2
        with self.assertRaises(ValidationError):
            self.invoice_item.save()

    def test_full_clinic_flow(self):
        self.assertEqual(self.invoice.items.count(), 1)
        self.assertEqual(self.invoice_item.medicine, self.medicine)
        self.assertEqual(self.medicine.stock_quantity, 100)
