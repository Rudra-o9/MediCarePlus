"""Patient CRUD, listing, detail pages, and purchase history views."""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.views.generic import DetailView

from .forms import PatientForm
from .models import Patient

from accounts.mixins import RoleRequiredMixin
from consultations.models import Consultation
from billing.models import InvoiceItemBatch


# ===============================
# ADD PATIENT
# ===============================
@login_required
def add_patient(request):
    """Create a patient record from the doctor/pharmacist side of the app."""

    if request.user.role not in ['DOCTOR', 'PHARMACIST']:
        return redirect('home')

    if not request.user.is_approved:
        return redirect('pending')

    if request.method == "POST":
        form = PatientForm(request.POST)

        if form.is_valid():
            patient = form.save(commit=False)
            patient.created_by = request.user
            patient.save()

            return redirect("patients:patient_detail", pk=patient.pk)

    else:
        form = PatientForm()

    return render(request, "patients/add_patient.html", {"form": form})


# ===============================
# PATIENT LIST
# ===============================
@login_required
def patient_list(request):
    """Searchable patient list scoped to records created by the current user."""

    if request.user.role not in ['DOCTOR', 'PHARMACIST']:
        return redirect('home')

    if not request.user.is_approved:
        return redirect('pending')

    query = request.GET.get("q")

    patients = request.user.created_patients.all()

    if query:
        patients = patients.filter(
            Q(full_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(medical_history__icontains=query) |
            Q(city__name__icontains=query)
        )

    context = {"patients": patients}

    return render(request, "patients/patient_list.html", context)


# ===============================
# PATIENT DETAIL
# ===============================
class PatientDetailView(RoleRequiredMixin, DetailView):
    """Full patient profile with linked consultation history."""

    model = Patient
    template_name = "patients/patient_detail.html"
    context_object_name = "patient"

    allowed_roles = ["DOCTOR", "PHARMACIST"]

    def get_queryset(self):
        return Patient.objects.all()

    def get_context_data(self, **kwargs):
        """Attach consultation history for faculty/demo explanation."""

        context = super().get_context_data(**kwargs)

        context["consultations"] = Consultation.objects.filter(
            patient=self.object
        )

        return context


# ===============================
# EDIT PATIENT
# ===============================
@login_required
def edit_patient(request, pk):
    """Update a patient record; only the creator can edit."""

    patient = get_object_or_404(Patient, pk=pk)

    if patient.created_by != request.user:
        return redirect("patients:patient_list")

    if request.method == "POST":

        form = PatientForm(request.POST, instance=patient)

        if form.is_valid():
            form.save()
            return redirect("patients:patient_detail", pk=patient.pk)

    else:
        form = PatientForm(instance=patient)

    return render(request, "patients/edit_patient.html", {"form": form})


# ===============================
# DELETE PATIENT
# ===============================
@login_required
def delete_patient(request, pk):
    """Delete a patient record; only the creator can delete."""

    patient = get_object_or_404(Patient, pk=pk)

    if patient.created_by != request.user:
        return redirect("patients:patient_list")

    if request.method == "POST":
        patient.delete()
        return redirect("patients:patient_list")

    return render(request, "patients/delete_patient.html", {"patient": patient})


# ===============================
# PURCHASE HISTORY
# ===============================
@login_required
def patient_purchase_history(request, pk):
    """Show medicines actually purchased by the patient from paid invoices."""

    patient = get_object_or_404(Patient, pk=pk)

    purchases = (
        InvoiceItemBatch.objects
        .select_related(
            "invoice_item__invoice",
            "invoice_item__medicine",
            "batch"
        )
        .filter(
            invoice_item__invoice__prescription__consultation__patient=patient,
            invoice_item__invoice__status="PAID"
        )
        .order_by("-invoice_item__invoice__created_at")
    )

    context = {
        "patient": patient,
        "purchases": purchases
    }

    return render(
        request,
        "patients/purchase_history.html",
        context
    )
