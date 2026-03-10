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


class ConsultationCreateView(RoleRequiredMixin, CreateView):
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
    model = Consultation
    template_name = 'consultations/consultation_detail.html'
    context_object_name = 'consultation'

    allowed_roles = ['DOCTOR', 'PHARMACIST']

    def get_queryset(self):
        if self.request.user.role == "DOCTOR":
            return Consultation.objects.filter(doctor=self.request.user)

        return Consultation.objects.all()


class AddDiagnosisView(RoleRequiredMixin, View):
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
    allowed_roles = ['DOCTOR']

    def get(self, request, pk):
        consultation = get_object_or_404(Consultation, pk=pk)

        if consultation.status != "OPEN":
            return redirect('consultations:consultation_detail', pk=pk)

        form = PrescriptionForm()
        formset = PrescriptionItemFormSet()

        return render(request, 'consultations/add_prescription.html', {
            'consultation': consultation,
            'form': form,
            'formset': formset
        })

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

        return render(request, 'consultations/add_prescription.html', {
            'consultation': consultation,
            'form': form,
            'formset': formset
        })


@login_required
def consultation_list(request):

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