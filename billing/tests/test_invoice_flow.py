from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier


class InvoiceFlowTest(TestCase):

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
        self.store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.store.staff.add(self.pharmacist)

        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="Supplier", phone="1234567890")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("0.00")
        )

        self.batch1 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B1",
            expiry_date=timezone.now().date() + timedelta(days=30),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=5
        )

        self.batch2 = Batch.objects.create(
            store=self.store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B2",
            expiry_date=timezone.now().date() + timedelta(days=60),
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=10
        )

        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store,
            routing_status="SENT"
        )

        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="2 times daily",
            duration_days=5,
            quantity_prescribed=8
        )

        self.invoice = Invoice.objects.create(prescription=self.prescription)
        self.invoice_item = InvoiceItem.objects.create(
            invoice=self.invoice,
            prescription_item=self.prescription_item,
            quantity=8,
            price_at_sale=Decimal("10.00")
        )

    def _pay_invoice(self, invoice=None, amount=None, received_by=None):
        invoice = invoice or self.invoice
        invoice.calculate_total()
        Payment.objects.create(
            invoice=invoice,
            amount=amount if amount is not None else invoice.total_amount,
            method="CASH",
            received_by=received_by or self.pharmacist
        )

    def test_full_payment_triggers_fifo_stock_deduction(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        self.invoice.refresh_from_db()
        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()

        self.assertEqual(self.invoice.status, "PAID")
        self.assertEqual(self.batch1.quantity, 0)
        self.assertEqual(self.batch2.quantity, 7)

    def test_overpayment_should_fail(self):
        self.invoice.calculate_total()

        with self.assertRaises(ValidationError):
            Payment.objects.create(
                invoice=self.invoice,
                amount=self.invoice.total_amount + Decimal("1.00"),
                method="CASH",
                received_by=self.pharmacist
            )

    def test_cannot_dispense_more_than_prescribed(self):
        with self.assertRaises(ValidationError):
            InvoiceItem.objects.create(
                invoice=self.invoice,
                prescription_item=self.prescription_item,
                quantity=20,
                price_at_sale=Decimal("10.00")
            )

    def test_cancel_invoice_restores_stock(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)
        InvoiceService.cancel_invoice(self.invoice, self.pharmacist)

        self.invoice.refresh_from_db()
        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()

        self.assertEqual(self.invoice.status, "CANCELLED")
        self.assertEqual(self.batch1.quantity, 5)
        self.assertEqual(self.batch2.quantity, 10)

    def test_prescription_status_updates(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        self.prescription.refresh_from_db()
        self.consultation.refresh_from_db()

        self.assertEqual(self.prescription.status, "BILLED")
        self.assertEqual(self.consultation.status, "CLOSED")

    def test_partial_payment_keeps_invoice_draft(self):
        self._pay_invoice(amount=Decimal("20.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "DRAFT")

    def test_expired_batch_not_used(self):
        Batch.objects.filter(pk=self.batch1.pk).update(
            expiry_date=timezone.now().date() - timedelta(days=1)
        )
        self.batch1.refresh_from_db()

        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()

        self.assertEqual(self.batch1.quantity, 5)
        self.assertEqual(self.batch2.quantity, 2)

    def test_cannot_modify_paid_invoice(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        with self.assertRaises(ValidationError):
            self.invoice_item.quantity = 2
            self.invoice_item.full_clean()

    def test_partial_then_full_payment_processes_correctly(self):
        self.invoice.calculate_total()
        total_amount = self.invoice.total_amount

        self._pay_invoice(amount=Decimal("20.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "DRAFT")

        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()
        self.assertEqual(self.batch1.quantity, 5)
        self.assertEqual(self.batch2.quantity, 10)

        remaining = total_amount - Decimal("20.00")
        self._pay_invoice(amount=remaining)
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        self.invoice.refresh_from_db()
        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()
        self.assertEqual(self.invoice.status, "PAID")
        self.assertEqual(self.batch1.quantity, 0)
        self.assertEqual(self.batch2.quantity, 7)

    def test_processing_payment_twice_does_not_double_deduct_stock(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()
        self.assertEqual(self.batch1.quantity, 0)
        self.assertEqual(self.batch2.quantity, 7)

    def test_multiple_invoices_respect_prescription_limit(self):
        self.prescription_item.quantity_prescribed = 10
        self.prescription_item.save()

        invoice1 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice1,
            prescription_item=self.prescription_item,
            quantity=4,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice1)
        InvoiceService.process_payment(invoice1, self.pharmacist)

        invoice2 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice2,
            prescription_item=self.prescription_item,
            quantity=3,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice2)
        InvoiceService.process_payment(invoice2, self.pharmacist)

        invoice3 = Invoice.objects.create(prescription=self.prescription)
        with self.assertRaises(ValidationError):
            InvoiceItem.objects.create(
                invoice=invoice3,
                prescription_item=self.prescription_item,
                quantity=5,
                price_at_sale=Decimal("10.00")
            )

    def test_multi_invoice_stock_insufficient(self):
        self.prescription_item.quantity_prescribed = 10
        self.prescription_item.save()

        self.batch1.quantity = 3
        self.batch1.save(update_fields=["quantity"])
        self.batch2.quantity = 5
        self.batch2.save(update_fields=["quantity"])

        invoice1 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice1,
            prescription_item=self.prescription_item,
            quantity=6,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice1)
        InvoiceService.process_payment(invoice1, self.pharmacist)

        invoice2 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice2,
            prescription_item=self.prescription_item,
            quantity=4,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice2)

        with self.assertRaises(ValidationError):
            InvoiceService.process_payment(invoice2, self.pharmacist)

    def test_cancel_one_of_multiple_invoices_updates_prescription_status(self):
        self.prescription_item.quantity_prescribed = 10
        self.prescription_item.save()

        invoice1 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice1,
            prescription_item=self.prescription_item,
            quantity=6,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice1)
        InvoiceService.process_payment(invoice1, self.pharmacist)

        invoice2 = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice2,
            prescription_item=self.prescription_item,
            quantity=4,
            price_at_sale=Decimal("10.00")
        )
        self._pay_invoice(invoice=invoice2)
        InvoiceService.process_payment(invoice2, self.pharmacist)

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "BILLED")

        InvoiceService.cancel_invoice(invoice2, self.pharmacist)

        self.prescription.refresh_from_db()
        self.consultation.refresh_from_db()
        self.assertEqual(self.prescription.status, "PARTIALLY_BILLED")
        self.assertEqual(self.consultation.status, "OPEN")

    def test_doctor_cannot_process_payment(self):
        self._pay_invoice()

        with self.assertRaises(ValidationError):
            InvoiceService.process_payment(self.invoice, self.doctor)

    def test_unapproved_pharmacist_cannot_process_payment(self):
        unapproved = CustomUser.objects.create_user(
            email="unapproved@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Unapproved",
            phone="1234567890",
            city=self.city,
            area=self.area,
            is_approved=False
        )

        self._pay_invoice()

        with self.assertRaises(ValidationError):
            InvoiceService.process_payment(self.invoice, unapproved)

    def test_doctor_cannot_cancel_invoice(self):
        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        with self.assertRaises(ValidationError):
            InvoiceService.cancel_invoice(self.invoice, self.doctor)

    def test_unapproved_pharmacist_cannot_cancel_invoice(self):
        unapproved = CustomUser.objects.create_user(
            email="unapproved2@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Unapproved2",
            phone="1234567891",
            city=self.city,
            area=self.area,
            is_approved=False
        )

        self._pay_invoice()
        InvoiceService.process_payment(self.invoice, self.pharmacist)

        with self.assertRaises(ValidationError):
            InvoiceService.cancel_invoice(self.invoice, unapproved)
