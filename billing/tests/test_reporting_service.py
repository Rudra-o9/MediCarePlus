from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from billing.services.report_service import ReportService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class ReportingServiceTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.doctor = CustomUser.objects.create_user(
            email="doc@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Doc",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.pharmacist = CustomUser.objects.create_user(
            email="pharma@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True
        )

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
        self.store = Store.objects.create(name="Adajan Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)
        self.other_store = Store.objects.create(name="Vesu Store", city=self.city, area=self.area)
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

        self.batch = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B1",
            expiry_date=timezone.now().date() + timedelta(days=30),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=100
        )
        self.other_batch = Batch.objects.create(
            store=self.other_store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B2",
            expiry_date=timezone.now().date() + timedelta(days=30),
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
            quantity_prescribed=40
        )

        other_consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.other_prescription = Prescription.objects.create(
            consultation=other_consultation,
            assigned_store=self.other_store,
            routing_status="SENT"
        )
        self.other_prescription_item = PrescriptionItem.objects.create(
            prescription=self.other_prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="2 times daily",
            duration_days=5,
            quantity_prescribed=40
        )

    def _create_paid_invoice(self, quantity, days_offset=0, prescription=None, prescription_item=None):
        prescription = prescription or self.prescription
        prescription_item = prescription_item or self.prescription_item
        invoice = Invoice.objects.create(prescription=prescription)

        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=prescription_item,
            quantity=quantity,
            price_at_sale=Decimal("10.00")
        )

        invoice.calculate_total()

        Payment.objects.create(
            invoice=invoice,
            amount=invoice.total_amount,
            method="CASH",
            received_by=self.pharmacist
        )

        if days_offset != 0:
            Invoice.objects.filter(pk=invoice.pk).update(
                created_at=timezone.now() - timedelta(days=days_offset)
            )
            invoice.refresh_from_db()

        InvoiceService.process_payment(invoice, self.pharmacist)

        return invoice

    def test_total_revenue(self):
        self._create_paid_invoice(2)
        self._create_paid_invoice(3)

        total = ReportService.total_revenue()
        self.assertEqual(total, Decimal("50.00"))

    def test_today_revenue(self):
        self._create_paid_invoice(4)

        revenue = ReportService.today_revenue()
        self.assertEqual(revenue, Decimal("40.00"))

    def test_monthly_revenue(self):
        self._create_paid_invoice(5)

        revenue = ReportService.monthly_revenue()
        self.assertEqual(revenue, Decimal("50.00"))

    def test_last_7_days_revenue(self):
        self._create_paid_invoice(1, days_offset=2)
        self._create_paid_invoice(2, days_offset=0)

        labels, values = ReportService.last_7_days_revenue()

        self.assertEqual(len(labels), 7)
        self.assertEqual(len(values), 7)
        self.assertTrue(any(v > 0 for v in values))

    def test_top_selling_medicines(self):
        self._create_paid_invoice(3)

        top = list(ReportService.top_selling_medicines())

        self.assertEqual(top[0]["prescription_item__medicine__name"], "Paracetamol")
        self.assertEqual(top[0]["total_sold"], 3)

    def test_sales_by_date_range_can_filter_by_store(self):
        self._create_paid_invoice(2)
        self._create_paid_invoice(
            4,
            prescription=self.other_prescription,
            prescription_item=self.other_prescription_item
        )

        invoices, total_revenue = ReportService.sales_by_date_range(store=self.store)

        self.assertEqual(invoices.count(), 1)
        self.assertEqual(total_revenue, Decimal("20.00"))

    def test_medicine_profit_report_can_filter_by_store(self):
        self._create_paid_invoice(2)
        self._create_paid_invoice(
            4,
            prescription=self.other_prescription,
            prescription_item=self.other_prescription_item
        )

        report, summary = ReportService.medicine_profit_report(store=self.store)

        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["quantity_sold"], 2)
        self.assertEqual(summary["total_revenue"], Decimal("20.00"))

    def test_medicine_profit_report_can_filter_by_date_range(self):
        self._create_paid_invoice(2, days_offset=40)
        self._create_paid_invoice(3, days_offset=2)

        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=5)

        report, summary = ReportService.medicine_profit_report(
            start_date=start_date,
            end_date=end_date,
            store=self.store,
        )

        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["quantity_sold"], 3)
        self.assertEqual(summary["total_revenue"], Decimal("30.00"))
