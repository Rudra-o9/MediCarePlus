from django.test import TestCase
from django.urls import reverse

from accounts.models import Area, City, CustomUser


class PharmacistDashboardViewTest(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Ahmedabad", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Navrangpura")
        self.pharmacist = CustomUser.objects.create_user(
            email="nav-pharma@test.com",
            password="pass123",
            role="PHARMACIST",
            full_name="Nav Pharmacist",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True,
        )

    def test_dashboard_renders_navigation_links(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse("pharmacist_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prescriptions")
        self.assertContains(response, "Invoices")
        self.assertContains(response, "Low Stock")
        self.assertContains(response, "Sales Report")
