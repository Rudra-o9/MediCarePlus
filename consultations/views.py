"""Doctor-side views for consultations, diagnoses, prescriptions, and routing.

Useful feature pointers:
- consultation creation and detail,
- adding diagnoses and prescription items,
- routing prescriptions to ranked nearby stores.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, DetailView
from django.urls import reverse
from accounts.mixins import RoleRequiredMixin
from patients.models import Patient
from .models import Consultation, Prescription
from .forms import ConsultationForm, DiagnosisFormSet, PrescriptionForm, PrescriptionItemFormSet
from django.views import View
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.utils import timezone
from billing.models import InvoiceItemBatch
from pharmacy.models import Store
from pharmacy.services import rank_stores_for_prescription


class ConsultationCreateView(RoleRequiredMixin, CreateView):
    """Create a consultation for a chosen patient."""
    model = Consultation
    form_class = ConsultationForm
    template_name = 'consultations/consultation_form.html'

    allowed_roles = ['DOCTOR']

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.doctor = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('patients:patient_detail', args=[self.patient.pk])


class ConsultationDetailView(RoleRequiredMixin, DetailView):
    """Consultation detail page plus ranked store suggestions for routing."""
    model = Consultation
    template_name = 'consultations/consultation_detail.html'
    context_object_name = 'consultation'

    allowed_roles = ['DOCTOR', 'PHARMACIST']

    def get_queryset(self):
        if self.request.user.role == "DOCTOR":
            return Consultation.objects.filter(doctor=self.request.user)

        return Consultation.objects.all()

    def get_context_data(self, **kwargs):
        # The first prescription is treated as the primary prescription for
        # routing because the current workflow creates one prescription record
        # per consultation.
        context = super().get_context_data(**kwargs)
        prescription = self.object.prescriptions.prefetch_related("items__medicine").first()
        previous_consultations = (
            Consultation.objects
            .filter(patient=self.object.patient)
            .exclude(pk=self.object.pk)
            .prefetch_related("diagnoses", "prescriptions__items__medicine")
            .select_related("doctor")[:5]
        )
        previous_purchases = (
            InvoiceItemBatch.objects
            .select_related(
                "invoice_item__medicine",
                "invoice_item__invoice__prescription__assigned_store"
            )
            .filter(
                invoice_item__invoice__prescription__consultation__patient=self.object.patient,
                invoice_item__invoice__status="PAID"
            )
            .exclude(invoice_item__invoice__prescription__consultation=self.object)
            .order_by("-invoice_item__invoice__created_at")[:8]
        )
        context["primary_prescription"] = prescription
        context["store_rankings"] = rank_stores_for_prescription(prescription) if prescription else []
        context["previous_consultations"] = previous_consultations
        context["previous_purchases"] = previous_purchases
        return context


class AddDiagnosisView(RoleRequiredMixin, View):
    """Add one or more diagnosis rows to an open consultation."""
    allowed_roles = ['DOCTOR']

    def get(self, request, pk):
        consultation = get_object_or_404(Consultation, pk=pk)

        if consultation.status != "OPEN":
            return redirect('consultations:consultation_detail', pk=pk)

        # allow extra diagnosis rows
        formset = DiagnosisFormSet(instance=consultation, queryset=consultation.diagnoses.all())

        return render(request, 'consultations/add_diagnosis.html', {
            'consultation': consultation,
            'formset': formset
        })

    def post(self, request, pk):
        consultation = get_object_or_404(Consultation, pk=pk)

        if consultation.status != "OPEN":
            return redirect('consultations:consultation_detail', pk=pk)

        formset = DiagnosisFormSet(request.POST, instance=consultation)

        if formset.is_valid():
            formset.save()

            return redirect('consultations:consultation_detail', pk=consultation.pk)

        return render(request, 'consultations/add_diagnosis.html', {
            'consultation': consultation,
            'formset': formset
        })


class AddPrescriptionView(RoleRequiredMixin, View):
    """Add prescription notes and medicine rows to an open consultation."""
    allowed_roles = ['DOCTOR']

    def _history_context(self, consultation):
        """Load a compact treatment history snapshot for the prescribing screen."""
        previous_consultations = (
            Consultation.objects
            .filter(patient=consultation.patient)
            .exclude(pk=consultation.pk)
            .prefetch_related("diagnoses")
            .select_related("doctor")[:3]
        )
        previous_purchases = (
            InvoiceItemBatch.objects
            .select_related("invoice_item__medicine")
            .filter(
                invoice_item__invoice__prescription__consultation__patient=consultation.patient,
                invoice_item__invoice__status="PAID"
            )
            .exclude(invoice_item__invoice__prescription__consultation=consultation)
            .order_by("-invoice_item__invoice__created_at")[:5]
        )
        return {
            "previous_consultations": previous_consultations,
            "previous_purchases": previous_purchases,
        }

    def get(self, request, pk):
        consultation = get_object_or_404(Consultation, pk=pk)

        if consultation.status != "OPEN":
            return redirect('consultations:consultation_detail', pk=pk)

        form = PrescriptionForm()
        formset = PrescriptionItemFormSet()

        context = {
            'consultation': consultation,
            'form': form,
            'formset': formset
        }
        context.update(self._history_context(consultation))

        return render(request, 'consultations/add_prescription.html', context)

    @transaction.atomic
    def post(self, request, pk):
        consultation = get_object_or_404(Consultation, pk=pk)

        if consultation.status != "OPEN":
            return redirect('consultations:consultation_detail', pk=pk)

        form = PrescriptionForm(request.POST)
        formset = PrescriptionItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():

            prescription = consultation.prescriptions.first()

            prescription.notes = form.cleaned_data["notes"]
            prescription.save()

            items = formset.save(commit=False)

            for item in items:
                item.prescription = prescription
                item.save()

            return redirect("consultations:consultation_detail", pk=pk)

        context = {
            'consultation': consultation,
            'form': form,
            'formset': formset
        }
        context.update(self._history_context(consultation))

        return render(request, 'consultations/add_prescription.html', context)


@login_required
@transaction.atomic
def route_prescription(request, prescription_id):
    """Doctor manually selects the best-ranked store and routes the prescription."""

    if request.user.role != "DOCTOR":
        raise PermissionDenied("Doctors only.")

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    prescription = get_object_or_404(
        Prescription.objects.select_related("consultation__doctor"),
        pk=prescription_id,
        consultation__doctor=request.user
    )

    store = get_object_or_404(Store, pk=request.POST.get("store_id"), is_active=True)

    # Only stores produced by the ranking logic are allowed, so a doctor cannot
    # post an arbitrary store ID that is outside the matching rules.
    allowed_store_ids = {
        row["store"].id
        for row in rank_stores_for_prescription(prescription)
    }

    if store.id not in allowed_store_ids:
        messages.error(request, "Selected store is not eligible for this prescription.")
        return redirect("consultations:consultation_detail", pk=prescription.consultation_id)

    prescription.assigned_store = store
    prescription.routing_status = "SENT"
    prescription.sent_at = timezone.now()
    prescription.save(update_fields=["assigned_store", "routing_status", "sent_at"])

    messages.success(request, f"Prescription sent to {store.name}.")

    return redirect("consultations:consultation_detail", pk=prescription.consultation_id)


@login_required
def consultation_list(request):
    """Doctor's consultation history list."""

    if request.user.role != "DOCTOR":
        raise PermissionDenied("Doctors only.")

    consultations = Consultation.objects.filter(
        doctor=request.user
    ).select_related("patient")

    return render(
        request,
        "consultations/consultation_list.html",
        {
            "consultations": consultations
        }
    )


@login_required
def start_consultation(request, patient_id):
    """Quick doctor workflow: start consultation and auto-create its prescription."""

    if request.user.role != "DOCTOR":
        raise PermissionDenied("Doctors only")

    patient = get_object_or_404(Patient, id=patient_id)

    if request.method == "POST":

        symptoms = request.POST.get("symptoms")
        blood_pressure = request.POST.get("blood_pressure")
        temperature = request.POST.get("temperature")
        pulse = request.POST.get("pulse")
        notes = request.POST.get("notes")

        consultation = Consultation.objects.create(
            patient=patient,
            doctor=request.user,
            symptoms=symptoms,
            blood_pressure=blood_pressure,
            temperature=temperature if temperature else None,
            pulse=pulse if pulse else None,
            notes=notes
        )

        Prescription.objects.create(
            consultation=consultation
        )

        return redirect("consultations:consultation_detail", pk=consultation.pk)

    return render(
        request,
        "consultations/start_consultation.html",
        {
            "patient": patient
        }
    )
