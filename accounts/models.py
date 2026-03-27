"""Authentication and location models used across the whole project.

Feature map:
- `City` and `Area` define where users, patients, and stores belong.
- `CustomUser` stores the role system for Admin, Doctor, and Pharmacist.
- Approval fields support the real-world admin verification workflow.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


# =========================
# City Model (Advanced)
# =========================
class City(models.Model):
    """Top-level location used to group users, patients, and pharmacy stores."""
    name = models.CharField(max_length=150)
    state = models.CharField(max_length=150)
    country = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Cities"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.state}, {self.country}"


class Area(models.Model):
    """Smaller locality inside a city.

    This is used for nearby-store matching so doctors can route prescriptions
    to pharmacists in the patient's practical buying area.
    """
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="areas"
    )
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["city__name", "name"]
        unique_together = ("city", "name")

    def __str__(self):
        return f"{self.name}, {self.city.name}"


# =========================
# Custom User Manager
# =========================
class CustomUserManager(BaseUserManager):
    """Custom manager because login is email-based instead of username-based."""
    def create_user(self, email, password=None, role='DOCTOR', **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)
        if "approval_status" not in extra_fields:
            extra_fields["approval_status"] = "APPROVED" if extra_fields.get("is_approved") else "PENDING"
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('is_approved', True)
        extra_fields.setdefault('approval_status', 'APPROVED')

        return self.create_user(email, password, **extra_fields)


# =========================
# Custom User Model
# =========================
class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Single user model for all system roles.

    Faculty explanation:
- `role` drives role-based dashboards and access checks.
- `city` and `area` support location-aware doctor/pharmacist/store workflows.
- `is_approved`, `approved_by`, and `approved_at` support admin-controlled onboarding.
    """

    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('DOCTOR', 'Doctor'),
        ('PHARMACIST', 'Pharmacist'),
    )
    APPROVAL_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    city = models.ForeignKey(
        City,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    is_approved = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default="PENDING",
    )
    rejection_reason = models.TextField(blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    license_number = models.CharField(max_length=100, blank=True, null=True)
    certificate = models.FileField(upload_to='certificates/', null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    approved_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_users'
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name', 'phone']


    def __str__(self):
        return self.email


class SystemSetting(models.Model):
    """Singleton-like admin configuration for security and operations policy.

    This lets the project expose system settings through the app UI instead of
    keeping every policy decision hidden in code.
    """

    allow_doctor_self_registration = models.BooleanField(default=True)
    allow_pharmacist_self_registration = models.BooleanField(default=True)
    doctor_approval_required = models.BooleanField(default=True)
    pharmacist_approval_required = models.BooleanField(default=True)
    expiry_alert_days = models.PositiveIntegerField(default=30)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "MediCarePlus System Settings"

    @classmethod
    def get_solo(cls):
        """Return the one settings row used across the application."""
        settings_obj, _ = cls.objects.get_or_create(pk=1)
        return settings_obj
