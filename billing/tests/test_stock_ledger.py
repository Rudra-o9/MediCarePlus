from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, StockMovement, Store, Supplier


User = get_user_model()


class StockLedgerTestCase(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = User.objects.create_user(
            email="doctor@test.com",
            password="test123",
            role="DOCTOR",
            full_name="Doctor",
            phone="9999999998",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.pharmacist = User.objects.create_user(
            email="pharma1@test.com",
            password="test123",
            role="PHARMACIST",
            full_name="Pharma One",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.store = Store.objects.create(name="Store 1", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)

        self.patient = Patient.objects.create(
            full_name="John Doe",
            age=30,
            gender="MALE",
            phone="9999999999",
            city=self.city,
            area=self.area,
            created_by=self.doctor
        )

        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier", phone="1111111111")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("5.00")
        )

        self.batch1 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B001",
            expiry_date=timezone.now().date() + timezone.timedelta(days=60),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.batch2 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B002",
            expiry_date=timezone.now().date() + timezone.timedelta(days=120),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )

        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="1 tab",
            frequency="Twice daily",
            duration_days=6,
            quantity_prescribed=12
        )

        self.invoice = Invoice.objects.create(prescription=self.prescription)

        self.invoice_item = InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=12,
            price_at_sale=Decimal("10.00")
        )

        self.invoice.calculate_total()

        Payment.objects.create(
            invoice=self.invoice,
            amount=self.invoice.total_amount,
            method="CASH",
            received_by=self.pharmacist
        )

    def test_fifo_deduction_and_ledger(self):
        InvoiceService.process_payment(self.invoice, performed_by=self.pharmacist)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "PAID")

        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()
        self.assertEqual(self.batch1.quantity, 0)
        self.assertEqual(self.batch2.quantity, 8)

        sales = StockMovement.objects.filter(movement_type="SALE")

        self.assertEqual(sales.count(), 2)
        self.assertTrue(all(s.store_id == self.store.id for s in sales))
        total_sold = sum(abs(s.quantity) for s in sales)
        self.assertEqual(total_sold, 12)
