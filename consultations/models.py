from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Max
from patients.models import Patient
from pharmacy.models import Medicine

class Consultation(models.Model):
    STATUS_CHOICES = (('OPEN','Open'),('CLOSED','Closed'))
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consultations")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, limit_choices_to={'role':'DOCTOR'}, related_name="consultations")
    visit_number = models.CharField(max_length=20, unique=True)
    consultation_date = models.DateTimeField(default=timezone.now)
    symptoms = models.TextField(blank=True)
    blood_pressure = models.CharField(max_length=20, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    follow_up_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-consultation_date']

    def save(self, *args, **kwargs):
        if not self.visit_number:
            year = timezone.now().year
            last_visit = Consultation.objects.filter(visit_number__startswith=f"CONS-{year}-").aggregate(Max('visit_number'))
            if last_visit['visit_number__max']:
                last_number = int(last_visit['visit_number__max'].split('-')[-1])
                new_number = last_number + 1
            else:
                new_number = 1
            self.visit_number = f"CONS-{year}-{str(new_number).zfill(5)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.visit_number

class Diagnosis(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="diagnoses")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class Prescription(models.Model):
    STATUS_CHOICES = (('PENDING','Pending'),('PARTIALLY_BILLED','Partially Billed'),('BILLED','Billed'),('CANCELLED','Cancelled'))
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='prescriptions')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prescription - {self.consultation.visit_number}"

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(Medicine, on_delete=models.SET_NULL, null=True, limit_choices_to={'is_active': True})
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration_days = models.PositiveIntegerField()
    quantity_prescribed = models.PositiveIntegerField()
    instructions = models.TextField(blank=True)

    def __str__(self):
        return f"{self.medicine.name} - {self.prescription.consultation.visit_number}"