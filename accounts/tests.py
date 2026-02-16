from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class AuthenticationTests(TestCase):

    def setUp(self):
        self.doctor_data = {
            'email': 'doctor@test.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123'
        }

        self.pharma_data = {
            'email': 'pharma@test.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123'
        }

    # ✅ Doctor Registration Test
    def test_doctor_registration(self):
        response = self.client.post(reverse('doctor_register'), self.doctor_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='doctor@test.com').exists())

    # ✅ Pharmacist Registration Test
    def test_pharmacist_registration(self):
        response = self.client.post(reverse('pharmacist_register'), self.pharma_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='pharma@test.com').exists())

    # ✅ Login Test
    def test_login(self):
        user = User.objects.create_user(
            email='login@test.com',
            password='StrongPass123',
            role='DOCTOR',
            is_approved=True
        )

        response = self.client.post(reverse('login'), {
            'username': 'login@test.com',
            'password': 'StrongPass123'
        })

        self.assertEqual(response.status_code, 302)

    # ✅ Dashboard Access Without Login
    def test_dashboard_requires_login(self):
        response = self.client.get('/accounts/doctor/dashboard/')
        self.assertEqual(response.status_code, 302)
        response = self.client.get('/accounts/pharmacist/dashboard/')
        self.assertEqual(response.status_code, 302) 