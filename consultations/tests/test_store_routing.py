from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Area, City, CustomUser
from billing.models import Invoice, InvoiceItem, Payment
from billing.services.invoice_service import InvoiceService
from consultations.models import Consultation, Prescription, PrescriptionItem
from patients.models import Patient
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier
from pharmacy.services import rank_stores_for_prescription


class StoreRoutingTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(
            name="Surat",
            state="Gujarat",
            country="India"
        )
        self.area_a = Area.objects.create(city=self.city, name="Adajan")
        self.area_b = Area.objects.create(city=self.city, name="Vesu")

        self.doctor = CustomUser.objects.create_user(
            email="doctor@test.com",
            password="pass123",
            role="DOCTOR",
            full_name="Dr Test",
            phone="9999999999",
            city=self.city,
            area=self.area_a,
            is_approved=True
        )

        self.pharmacist = CustomUser.objects.create_user(
            email="pharmacist@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Pharma Test",
            phone="8888888888",
            city=self.city,
            area=self.area_a,
            is_approved=True
        )

        self.patient = Patient.objects.create(
            full_name="John Doe",
            age=30,
            gender="MALE",
            phone="7777777777",
            city=self.city,
            area=self.area_a,
            created_by=self.doctor
        )

        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor
        )
        self.prescription = Prescription.objects.create(consultation=self.consultation)

        self.category = MedicineCategory.objects.create(name="General")
        self.supplier = Supplier.objects.create(name="ABC Pharma", phone="1111111111")

        self.medicine_1 = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price=Decimal("10.00"),
            gst_percentage=Decimal("5.00")
        )
        self.medicine_2 = Medicine.objects.create(
            name="Cetirizine",
            category=self.category,
            default_selling_price=Decimal("12.00"),
            gst_percentage=Decimal("5.00")
        )

        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine_1,
            dosage="500mg",
            frequency="Twice daily",
            duration_days=5,
            quantity_prescribed=10
        )
        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine_2,
            dosage="10mg",
            frequency="Once daily",
            duration_days=3,
            quantity_prescribed=6
        )

        self.store_full = Store.objects.create(
            name="Adajan Medico",
            city=self.city,
            area=self.area_a,
            phone="12345"
        )
        self.store_full.staff.add(self.pharmacist)

        self.store_partial = Store.objects.create(
            name="Vesu Care",
            city=self.city,
            area=self.area_b,
            phone="67890"
        )

        Batch.objects.create(
            store=self.store_full,
            supplier=self.supplier,
            medicine=self.medicine_1,
            batch_number="P1",
            expiry_date="2030-01-01",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=20
        )
        Batch.objects.create(
            store=self.store_full,
            supplier=self.supplier,
            medicine=self.medicine_2,
            batch_number="C1",
            expiry_date="2030-01-01",
            purchase_price=Decimal("6.00"),
            selling_price=Decimal("12.00"),
            quantity=20
        )
        Batch.objects.create(
            store=self.store_partial,
            supplier=self.supplier,
            medicine=self.medicine_1,
            batch_number="P2",
            expiry_date="2030-01-01",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("10.00"),
            quantity=4
        )

    def test_store_ranking_prefers_full_match_in_same_area(self):
        rankings = rank_stores_for_prescription(self.prescription)

        self.assertEqual(rankings[0]["store"], self.store_full)
        self.assertTrue(rankings[0]["is_full_match"])
        self.assertFalse(rankings[1]["is_full_match"])

    def test_doctor_can_route_prescription_to_ranked_store(self):
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("consultations:route_prescription", args=[self.prescription.id]),
            {"store_id": self.store_full.id}
        )

        self.assertEqual(response.status_code, 302)

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.assigned_store, self.store_full)
        self.assertEqual(self.prescription.routing_status, "SENT")

    def test_pharmacist_invoice_uses_only_selected_store_stock(self):
        self.prescription.assigned_store = self.store_full
        self.prescription.routing_status = "SENT"
        self.prescription.save(update_fields=["assigned_store", "routing_status"])

        low_stock_batch = Batch.objects.get(store=self.store_full, medicine=self.medicine_2)
        low_stock_batch.quantity = 3
        low_stock_batch.save(update_fields=["quantity"])

        self.client.force_login(self.pharmacist)

        response = self.client.get(
            reverse("billing:create_invoice", args=[self.prescription.id])
        )

        self.assertEqual(response.status_code, 302)

        invoice = Invoice.objects.get(prescription=self.prescription)
        invoice_items = list(invoice.items.order_by("medicine__name"))

        self.assertEqual(len(invoice_items), 2)
        self.assertEqual(invoice_items[0].quantity, 3)
        self.assertEqual(invoice_items[1].quantity, 10)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.routing_status, "RECEIVED")

    def test_routing_status_moves_to_completed_after_full_payment(self):
        self.prescription.assigned_store = self.store_full
        self.prescription.routing_status = "SENT"
        self.prescription.save(update_fields=["assigned_store", "routing_status"])

        invoice = Invoice.objects.create(prescription=self.prescription)
        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=self.prescription.items.get(medicine=self.medicine_1),
            quantity=10,
            price_at_sale=Decimal("10.00")
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=self.prescription.items.get(medicine=self.medicine_2),
            quantity=6,
            price_at_sale=Decimal("12.00")
        )
        invoice.calculate_total()
        Payment.objects.create(
            invoice=invoice,
            amount=invoice.total_amount,
            method="CASH",
            received_by=self.pharmacist
        )

        InvoiceService.process_payment(invoice, self.pharmacist)

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "BILLED")
        self.assertEqual(self.prescription.routing_status, "COMPLETED")

    def test_consultation_detail_shows_previous_treatment_context(self):
        previous_consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            symptoms="Fever"
        )
        previous_prescription = Prescription.objects.create(
            consultation=previous_consultation,
            assigned_store=self.store_full,
            routing_status="COMPLETED",
            status="BILLED"
        )
        previous_item = PrescriptionItem.objects.create(
            prescription=previous_prescription,
            medicine=self.medicine_1,
            dosage="500mg",
            frequency="Twice daily",
            duration_days=3,
            quantity_prescribed=2
        )
        invoice = Invoice.objects.create(prescription=previous_prescription)
        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=previous_item,
            quantity=2,
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

        self.client.force_login(self.doctor)
        response = self.client.get(
            reverse("consultations:consultation_detail", args=[self.consultation.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previous Treatments")
        self.assertContains(response, previous_consultation.visit_number)
        self.assertContains(response, "Recent Purchase History")
        self.assertContains(response, self.store_full.phone)
