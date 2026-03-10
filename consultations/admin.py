from django.contrib import admin
from .models import Consultation, Diagnosis, Prescription, PrescriptionItem


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('visit_number', 'patient', 'doctor', 'status', 'consultation_date')
    list_filter = ('status',)
    search_fields = ('visit_number',)


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'consultation', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ('prescription', 'medicine', 'quantity_prescribed')