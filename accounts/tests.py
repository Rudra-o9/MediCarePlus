from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import Area, City, SystemSetting
from pharmacy.models import Batch, Medicine, MedicineCategory, Store, Supplier
from accounts.forms import BatchProcurementForm

User = get_user_model()


class AuthenticationTests(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")
        self.doctor_data = {
            'email': 'doctor@test.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
            'full_name': 'Test Doctor',
            'phone': '9999999999',
            'city': self.city.id,
            'area': self.area.id,
        }

        self.pharma_data = {
            'email': 'pharma@test.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
            'full_name': 'Test Pharmacist',
            'phone': '8888888888',
            'city': self.city.id,
            'area': self.area.id,
        }

    # ✅ Doctor Registration Test
    def test_doctor_registration(self):
        response = self.client.post(
            reverse('doctor_register'),
            self.doctor_data
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(email='doctor@test.com').exists()
        )

    # ✅ Pharmacist Registration Test
    def test_pharmacist_registration(self):
        response = self.client.post(
            reverse('pharmacist_register'),
            self.pharma_data
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.filter(email='pharma@test.com').exists()
        )

    # ✅ Login Test
    def test_login(self):
        user = User.objects.create_user(
            email='login@test.com',
            password='StrongPass123',
            role='DOCTOR',
            is_approved=True,
            full_name='Login Doctor',
            phone='7777777777',
            city=self.city,
            area=self.area
        )

        response = self.client.post(reverse('login'), {
            'username': 'login@test.com',
            'password': 'StrongPass123'
        })

        self.assertEqual(response.status_code, 302)

    # ✅ Dashboard Access Without Login
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('doctor_dashboard'))
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse('pharmacist_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_doctor_logout_redirects_to_home_and_clears_session(self):
        user = User.objects.create_user(
            email='doctor-logout@test.com',
            password='StrongPass123',
            role='DOCTOR',
            is_approved=True,
            full_name='Logout Doctor',
            phone='7777777778',
            city=self.city,
            area=self.area
        )
        self.client.force_login(user)

        response = self.client.post(reverse('logout'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse('home'))
        follow_response = self.client.get(reverse('doctor_dashboard'))
        self.assertEqual(follow_response.status_code, 302)

    def test_pharmacist_logout_redirects_to_home_and_clears_session(self):
        user = User.objects.create_user(
            email='pharma-logout@test.com',
            password='StrongPass123',
            role='PHARMACIST',
            is_approved=True,
            full_name='Logout Pharmacist',
            phone='8888888889',
            city=self.city,
            area=self.area
        )
        self.client.force_login(user)

        response = self.client.post(reverse('logout'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse('home'))
        follow_response = self.client.get(reverse('pharmacist_dashboard'))
        self.assertEqual(follow_response.status_code, 302)


class AdminOperationsTests(TestCase):

    def setUp(self):
        self.city = City.objects.create(name="Surat", state="Gujarat", country="India")
        self.area = Area.objects.create(city=self.city, name="Adajan")

        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="StrongPass123",
            role="ADMIN",
            full_name="Admin",
            phone="9999999999",
            city=self.city,
            area=self.area,
            is_approved=True
        )
        self.pharmacist = User.objects.create_user(
            email="pharma-ops@test.com",
            password="StrongPass123",
            role="PHARMACIST",
            full_name="Ops Pharmacist",
            phone="8888888888",
            city=self.city,
            area=self.area,
            is_approved=True
        )

        self.category = MedicineCategory.objects.create(name="General")
        self.medicine = Medicine.objects.create(
            name="Paracetamol",
            category=self.category,
            default_selling_price="10.00",
            gst_percentage="5.00"
        )
        self.supplier = Supplier.objects.create(name="ABC Pharma", phone="1234567890")

    def test_admin_can_create_store_from_ui(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("store_management"), {
            "name": "Main Store",
            "city": self.city.id,
            "area": self.area.id,
            "address": "Adajan Road",
            "phone": "9990001111",
            "email": "store@example.com",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Store.objects.filter(name="Main Store").exists())

    def test_admin_can_assign_pharmacist_to_store(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("assign_store_staff", args=[store.id]), {
            f"store-{store.id}-pharmacist": self.pharmacist.id,
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn(self.pharmacist, store.staff.all())

    def test_admin_can_remove_pharmacist_from_store(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        store.staff.add(self.pharmacist)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("remove_store_staff", args=[store.id, self.pharmacist.id]))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(self.pharmacist, store.staff.all())

    def test_admin_can_edit_store(self):
        store = Store.objects.create(
            name="Main Store",
            city=self.city,
            area=self.area,
            address="Old Address",
            phone="1111111111",
            email="old@store.com",
            is_active=True,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("edit_store", args=[store.id]), {
            f"edit-store-{store.id}-name": "Updated Store",
            f"edit-store-{store.id}-city": self.city.id,
            f"edit-store-{store.id}-area": self.area.id,
            f"edit-store-{store.id}-address": "New Address",
            f"edit-store-{store.id}-phone": "2222222222",
            f"edit-store-{store.id}-email": "updated@store.com",
            f"edit-store-{store.id}-is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        store.refresh_from_db()
        self.assertEqual(store.name, "Updated Store")
        self.assertEqual(store.address, "New Address")
        self.assertEqual(store.phone, "2222222222")
        self.assertEqual(store.email, "updated@store.com")

    def test_admin_can_delete_store(self):
        store = Store.objects.create(name="Delete Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("delete_store", args=[store.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Store.objects.filter(id=store.id).exists())

    def test_admin_can_procure_batch_from_ui(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("procurement_management"), {
            "store": store.id,
            "supplier": self.supplier.id,
            "medicine": self.medicine.id,
            "batch_number": "B-NEW-1",
            "expiry_date": "2030-01-01",
            "purchase_price": "5.00",
            "selling_price": "10.00",
            "quantity": "25",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Batch.objects.filter(store=store, batch_number="B-NEW-1").exists())

    def test_procurement_duplicate_batch_shows_validation_error(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        Batch.objects.create(
            store=store,
            supplier=self.supplier,
            medicine=self.medicine,
            batch_number="B-DUP-1",
            expiry_date="2030-01-01",
            purchase_price="5.00",
            selling_price="10.00",
            quantity=25,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("procurement_management"), {
            "store": store.id,
            "supplier": self.supplier.id,
            "medicine": self.medicine.id,
            "batch_number": "B-DUP-1",
            "expiry_date": "2030-01-01",
            "purchase_price": "5.00",
            "selling_price": "10.00",
            "quantity": "25",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This batch number already exists for the selected store and medicine.",
        )

    def test_procurement_past_expiry_shows_validation_error(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("procurement_management"), {
            "store": store.id,
            "supplier": self.supplier.id,
            "medicine": self.medicine.id,
            "batch_number": "B-OLD-1",
            "expiry_date": "2024-01-01",
            "purchase_price": "5.00",
            "selling_price": "10.00",
            "quantity": "25",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cannot create batch with past expiry date.")

    def test_procurement_form_excludes_stores_with_mismatched_area(self):
        other_city = City.objects.create(name="Ahmedabad", state="Gujarat", country="India")
        mismatched_store = Store.objects.create(
            name="Broken Store",
            city=other_city,
            area=self.area,
        )
        valid_store = Store.objects.create(name="Valid Store", city=self.city, area=self.area)

        form = BatchProcurementForm()

        self.assertIn(valid_store, form.fields["store"].queryset)
        self.assertNotIn(mismatched_store, form.fields["store"].queryset)

    def test_procurement_zero_quantity_shows_validation_error(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("procurement_management"), {
            "store": store.id,
            "supplier": self.supplier.id,
            "medicine": self.medicine.id,
            "batch_number": "B-ZERO-QTY",
            "expiry_date": "2030-01-01",
            "purchase_price": "5.00",
            "selling_price": "10.00",
            "quantity": "0",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Batch quantity must be greater than zero.")

    def test_procurement_zero_price_shows_validation_error(self):
        store = Store.objects.create(name="Main Store", city=self.city, area=self.area)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("procurement_management"), {
            "store": store.id,
            "supplier": self.supplier.id,
            "medicine": self.medicine.id,
            "batch_number": "B-ZERO-PRICE",
            "expiry_date": "2030-01-01",
            "purchase_price": "0",
            "selling_price": "10.00",
            "quantity": "5",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase price must be greater than zero.")

    def test_admin_can_create_category_from_ui(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("manage_categories"), {
            "name": "Antibiotics",
            "description": "Used for bacterial infection",
            "parent": "",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(MedicineCategory.objects.filter(name="Antibiotics").exists())

    def test_admin_can_create_supplier_from_ui(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("manage_suppliers"), {
            "name": "Health Supplier",
            "contact_person": "Amit",
            "phone": "9998887777",
            "email": "health@supplier.com",
            "gst_number": "GST123",
            "address": "Surat",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Supplier.objects.filter(name="Health Supplier").exists())

    def test_admin_can_create_medicine_from_ui(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("manage_medicines"), {
            "name": "Cetirizine",
            "manufacturer": "ABC Labs",
            "description": "Anti-allergy tablet",
            "default_selling_price": "12.50",
            "gst_percentage": "5.00",
            "category": self.category.id,
            "hsn_code": "3004",
            "low_stock_threshold": "8",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Medicine.objects.filter(name="Cetirizine").exists())

    def test_admin_can_update_system_settings(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("system_settings"), {
            "allow_doctor_self_registration": "on",
            "allow_pharmacist_self_registration": "",
            "doctor_approval_required": "on",
            "pharmacist_approval_required": "",
            "expiry_alert_days": "45",
        })

        self.assertEqual(response.status_code, 302)
        settings_obj = SystemSetting.get_solo()
        self.assertTrue(settings_obj.allow_doctor_self_registration)
        self.assertFalse(settings_obj.allow_pharmacist_self_registration)
        self.assertTrue(settings_obj.doctor_approval_required)
        self.assertFalse(settings_obj.pharmacist_approval_required)
        self.assertEqual(settings_obj.expiry_alert_days, 45)

    def test_disabled_pharmacist_registration_shows_closed_page(self):
        settings_obj = SystemSetting.get_solo()
        settings_obj.allow_pharmacist_self_registration = False
        settings_obj.save(update_fields=["allow_pharmacist_self_registration"])

        response = self.client.get(reverse("pharmacist_register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Closed")

    def test_reject_user_marks_status_and_keeps_account(self):
        doctor = User.objects.create_user(
            email="reject-doctor@test.com",
            password="StrongPass123",
            role="DOCTOR",
            full_name="Reject Doctor",
            phone="9991234567",
            city=self.city,
            area=self.area,
            is_approved=False,
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("reject_user", args=[doctor.id]), {
            "rejection_reason": "License document is not valid.",
        })

        self.assertEqual(response.status_code, 302)
        doctor.refresh_from_db()
        self.assertEqual(doctor.approval_status, "REJECTED")
        self.assertEqual(doctor.rejection_reason, "License document is not valid.")
        self.assertFalse(doctor.is_approved)

    def test_rejected_user_sees_rejection_message_on_pending_page(self):
        doctor = User.objects.create_user(
            email="pending-reject@test.com",
            password="StrongPass123",
            role="DOCTOR",
            full_name="Pending Reject Doctor",
            phone="9991234568",
            city=self.city,
            area=self.area,
            is_approved=False,
            approval_status="REJECTED",
            rejection_reason="Certificate upload was unclear.",
        )
        self.client.force_login(doctor)

        response = self.client.get(reverse("pending"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Decision Available")
        self.assertContains(response, "Certificate upload was unclear.")
