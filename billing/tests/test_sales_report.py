from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from billing.models import Invoice
from django.contrib.auth import get_user_model
from accounts.models import Area, City
from patients.models import Patient
from consultations.models import Consultation, Prescription
from pharmacy.models import Store

User = get_user_model()

class SalesReportViewTest(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")
        # Create doctor user
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass",
            role="ADMIN",
            full_name="Test Admin",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        # Create patient
        self.patient = Patient.objects.create(
            full_name="Test Patient",
            age=30,
            gender="MALE",
            phone="8888888888",
            city=self.city,
            area=self.area,
            created_by=self.user
        )

        # Create consultation (IMPORTANT STEP YOU WERE MISSING)
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.user
        )

        self.store = Store.objects.create(
            name="Main Store",
            city=self.city,
            area=self.area
        )
        self.other_store = Store.objects.create(
            name="Branch Store",
            city=self.city,
            area=self.area
        )

        # Create prescription (linked to consultation)
        self.prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.store
        )
        self.other_prescription = Prescription.objects.create(
            consultation=self.consultation,
            assigned_store=self.other_store
        )

        # Create invoices
        Invoice.objects.create(
            prescription=self.prescription,
            invoice_number="INV-TEST-00001",
            total_amount=Decimal("100.00"),
            status="PAID"
        )

        Invoice.objects.create(
            prescription=self.other_prescription,
            invoice_number="INV-TEST-00002",
            total_amount=Decimal("200.00"),
            status="PAID"
        )

    def test_sales_report_total(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("billing:sales_report"))
        self.assertEqual(response.status_code, 200)

        # Total should be 300 (only PAID)
        self.assertContains(response, "300")

    def test_date_filter(self):
        today = timezone.now().date()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("billing:sales_report"),
            {
                "start_date": today,
                "end_date": today,
            }
        )

        self.assertEqual(response.status_code, 200)

    def test_admin_can_filter_sales_report_by_store(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("billing:sales_report"),
            {"store": self.store.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
        self.assertNotContains(response, "200.00")
