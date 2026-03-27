from decimal import Decimal
from threading import Thread

from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class ConcurrencyTestCase(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = CustomUser.objects.create_user(
            email="doctor@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Doctor",
            phone="9999999998",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.pharmacist = CustomUser.objects.create_user(
            email="pharma@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.store = Store.objects.create(name="Adajan Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)

        self.patient = Patient.objects.create(
            full_name="Test Patient",
            age=30,
            gender="MALE",
            phone="7777777777",
            city=self.city,
            area=self.area,
            created_by=self.doctor
        )

        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )

        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier", phone="1234567890")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("0.00")
        )

        self.batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B1",
            expiry_date=timezone.now().date() + timezone.timedelta(days=30),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="2 times daily",
            duration_days=5,
            quantity_prescribed=10
        )

        self.invoice1 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=self.invoice1,
            prescription_item=self.prescription_item,
            quantity=10,
            price_at_sale=Decimal("10.00")
        )
        self.invoice1.calculate_total()

        Payment.objects.create(
            invoice=self.invoice1,
            amount=self.invoice1.total_amount,
            method="CASH",
            received_by=self.pharmacist
        )

    def _process_payment(self):
        try:
            InvoiceService.process_payment(self.invoice1, self.pharmacist)
        except Exception:
            pass

    def test_double_processing_concurrently(self):
        t1 = Thread(target=self._process_payment)
        t2 = Thread(target=self._process_payment)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.batch.refresh_from_db()

        self.assertEqual(self.batch.quantity, 0)
