"""Patient records and their location-aware demographic details."""

from django.db import models
from django.conf import settings
from accounts.models import Area, City


class Patient(models.Model):
    """Central patient master record.

    Faculty explanation:
- doctors/pharmacists can create patient records,
- consultations and prescription history hang off this model,
- city/area help match prescriptions with nearby pharmacy stores.
    """

    GENDER_CHOICES = (
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
    )

    full_name = models.CharField(max_length=150)
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    phone = models.CharField(max_length=15)

    city = models.ForeignKey(
        City,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patients"
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patients"
    )

    address = models.TextField(blank=True)

    medical_history = models.TextField(
        blank=True,
        help_text="Any past diseases, allergies, or important medical notes."
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_patients"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name
