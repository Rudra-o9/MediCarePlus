from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Area, City
from billing.models import Invoice, InvoiceItem
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Medicine, MedicineCategory, Store


User = get_user_model()


class GSTCalculationTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = User.objects.create_user(
            email="doctor1@test.com",
            password="testpass123",
            role="DOCTOR",
            full_name="Test Doctor",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.patient = Patient.objects.create(
            full_name="Test Patient",
            age=30,
            gender="MALE",
            phone="9999999999",
            city=self.city,
            area=self.area,
            created_by=self.doctor
        )

        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.store = Store.objects.create(name="GST Store", city=self.city, area=self.area)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )

        self.category = MedicineCategory.objects.create(name="General")
        self.medicine = Medicine.objects.create(
            name="TestMed",
            category=self.category,
            default_selling_price=Decimal("99.99"),
            gst_percentage=Decimal("18.00")
        )

        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="1 tablet",
            frequency="Twice daily",
            duration_days=5,
            quantity_prescribed=5
        )

        self.invoice = Invoice.objects.create(prescription=self.prescription)

    def test_gst_calculation(self):
        item = InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=3,
            price_at_sale=Decimal("99.99")
        )

        self.assertEqual(item.subtotal, Decimal("299.97"))
        self.assertEqual(item.cgst_amount, Decimal("27.00"))
        self.assertEqual(item.sgst_amount, Decimal("27.00"))
        self.assertEqual(item.total_with_tax, Decimal("353.96"))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("353.96"))
