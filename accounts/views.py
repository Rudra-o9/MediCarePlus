"""Views for authentication, dashboards, approvals, and admin operations.

Navigation guide for faculty/demo:
- registration + login flow starts here,
- role-based dashboard redirection happens here,
- admin approval, store management, and procurement UI also live here.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from .forms import (
    BatchProcurementForm,
    DoctorRegisterForm,
    PharmacistRegisterForm,
    StoreForm,
    StoreStaffAssignmentForm,
    SystemSettingForm,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from patients.models import Patient
from pharmacy.models import Batch, Medicine, Store, Supplier
from .models import Area, City, SystemSetting
from pharmacy.services import (
    get_low_stock_medicines,
    get_near_expiry_batches,
    get_expired_batches
)
from billing.services.report_service import ReportService
import json
from accounts.services.dashboard_service import DashboardService
from billing.models import InvoiceItem, Invoice
from consultations.models import Prescription
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
from pharmacy.models import Batch
from django.utils import timezone
from core.utils.activity_logger import log_activity
from core.models import ActivityLog
from core.models import Notification


def ensure_admin(user):
    """Shared guard for admin-only pages."""
    if user.role != "ADMIN":
        raise PermissionDenied("Admin access required")


def doctor_register(request):
    """Doctor self-registration request.

    Admin approval is still required before the doctor can use the system.
    """
    settings_obj = SystemSetting.get_solo()

    if not settings_obj.allow_doctor_self_registration:
        return render(request, "accounts/registration_closed.html", {"role": "Doctor"})

    if request.method == "POST":
        form = DoctorRegisterForm(request.POST, request.FILES)

        if form.is_valid():

            user = form.save()
            if not settings_obj.doctor_approval_required:
                user.is_approved = True
                user.approval_status = "APPROVED"
                user.approved_at = timezone.now()
                user.save(update_fields=["is_approved", "approval_status", "approved_at"])

            from core.models import Notification

            Notification.objects.create(
                title="New Doctor Registered",
                message=f"{user.full_name} has registered as Doctor",
                notification_type="INFO"
            )

            return redirect("login")

    else:
        form = DoctorRegisterForm()

    return render(request, "accounts/register.html", {
        "form": form,
        "role": "Doctor"
    })


def pharmacist_register(request):
    """Pharmacist self-registration request with pending approval workflow."""
    settings_obj = SystemSetting.get_solo()

    if not settings_obj.allow_pharmacist_self_registration:
        return render(request, "accounts/registration_closed.html", {"role": "Pharmacist"})

    if request.method == 'POST':
        form = PharmacistRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            if not settings_obj.pharmacist_approval_required:
                user.is_approved = True
                user.approval_status = "APPROVED"
                user.approved_at = timezone.now()
                user.save(update_fields=["is_approved", "approval_status", "approved_at"])

        from core.models import Notification

        Notification.objects.create(
            title="New Pharmacist Registered",
            message=f"{user.full_name} has registered as Pharmacist",
            notification_type="INFO"
        )

        return redirect('login')
    else:
        form = PharmacistRegisterForm()

    return render(request, 'accounts/register.html', {'form': form, 'role': 'Pharmacist'})

@login_required
def role_redirect(request):
    """Send the user to the correct dashboard after login."""
    user = request.user

    if user.approval_status == "REJECTED":
        return redirect('pending')

    if not user.is_approved:
        return redirect('pending')

    if user.role == 'ADMIN':
        return redirect('admin_dashboard')

    elif user.role == 'DOCTOR':
        return redirect('doctor_dashboard')

    elif user.role == "PHARMACIST":
        return redirect("/pharmacy/dashboard/")

    return redirect('login')

@login_required
def pending_view(request):
    context = {
        "is_rejected": request.user.approval_status == "REJECTED",
        "rejection_reason": request.user.rejection_reason,
    }
    return render(request, 'accounts/pending.html', context)

@login_required
def doctor_dashboard(request):
    """Doctor dashboard with patient and consultation summary data."""

    if request.user.role != "DOCTOR":
        raise PermissionDenied("Access restricted to doctors.")

    if not request.user.is_approved:
        return redirect("pending")

    from consultations.models import Consultation, Prescription
    from patients.models import Patient
    from django.utils import timezone

    today = timezone.now().date()

    # ---- BASIC STATS ----

    total_patients = Patient.objects.count()

    today_consultations = Consultation.objects.filter(
        doctor=request.user,
        consultation_date__date=today
    ).count()

    open_consultations = Consultation.objects.filter(
        doctor=request.user,
        status="OPEN"
    ).count()

    pending_prescriptions = Prescription.objects.filter(
        consultation__doctor=request.user,
        status="PENDING"
    ).count()

    # ---- RECENT DATA ----

    recent_patients = Patient.objects.order_by("-created_at")[:5]

    recent_consultations = Consultation.objects.filter(
        doctor=request.user
    ).select_related("patient")[:5]

    context = {
        "total_patients": total_patients,
        "today_consultations": today_consultations,
        "open_consultations": open_consultations,
        "pending_prescriptions": pending_prescriptions,
        "recent_patients": recent_patients,
        "recent_consultations": recent_consultations,
        "user": request.user
    }

    return render(
        request,
        "accounts/doctor_dashboard.html",
        context
    )

@login_required
def pharmacist_dashboard(request):
    """Primary pharmacist dashboard used from the accounts-side route.

    The same business metrics are also exposed through `/pharmacy/dashboard/`,
    but this version is responsible for the richer dashboard analytics.
    """

    user = request.user

    if user.role != "PHARMACIST":
        raise PermissionDenied("Access restricted to pharmacist.")

    if not user.is_approved:
        raise PermissionDenied("User not approved.")


    # ---- PERIOD FILTER ----
    period = int(request.GET.get("period", 6))
    current_store = user.stores.filter(is_active=True).first()
    pending_prescription_count = 0
    draft_invoice_count = 0
    paid_invoice_count = 0

    if current_store:
        pending_prescription_count = Prescription.objects.filter(
            assigned_store=current_store,
            status__in=["PENDING", "PARTIALLY_BILLED"],
            routing_status__in=["SENT", "RECEIVED", "PARTIALLY_FULFILLED"],
        ).count()
        draft_invoice_count = Invoice.objects.filter(
            prescription__assigned_store=current_store,
            status="DRAFT",
        ).count()
        paid_invoice_count = Invoice.objects.filter(
            prescription__assigned_store=current_store,
            status="PAID",
        ).count()


    # ---- DASHBOARD STATS ----
    context = DashboardService.pharmacist_dashboard_data()


    # ---- MONTHLY PROFIT DATA ----
    labels, revenue_values, profit_values = ReportService.monthly_profit_trend(period)
    cat_labels, cat_values = ReportService.sales_by_category()
    top_today_labels, top_today_values = ReportService.top_medicines_today()


    analytics = ReportService.dashboard_analytics()

    context.update({
        "profit_labels_json": json.dumps(labels),
        "revenue_values_json": json.dumps(revenue_values),
        "profit_values_json": json.dumps(profit_values),
        "selected_period": period,

        "category_labels_json": json.dumps(cat_labels),
        "category_values_json": json.dumps(cat_values),

        "top_today_labels_json": json.dumps(top_today_labels),
        "top_today_values_json": json.dumps(top_today_values),

        "monthly_growth": analytics["monthly_growth"],
        "most_profitable": analytics["most_profitable"],
        "stock_value": analytics["stock_value"]
    })

    context.update({
        "has_trend_data": any(json.loads(context["trend_values_json"])),
        "has_top_medicine_data": bool(json.loads(context["top_values_json"])),
        "has_category_data": bool(cat_labels),
        "has_today_top_data": bool(top_today_labels),
        "current_store": current_store,
        "no_store_assigned": current_store is None,
        "pending_prescription_count": pending_prescription_count,
        "draft_invoice_count": draft_invoice_count,
        "paid_invoice_count": paid_invoice_count,
    })


    context["user"] = user

    return render(
        request,
        "accounts/pharmacist_dashboard.html",
        context
    )

def home(request):
    """Public landing page with role-aware redirect for logged-in users."""
    user = request.user

    if user.is_authenticated:

        # Admin first
        # if user.is_superuser:
        #     return redirect('/admin/')

        # If not approved
        if user.approval_status == "REJECTED":
            return redirect('pending')

        if not user.is_approved:
            return redirect('pending')

        # Role-based redirect
        if user.role == 'DOCTOR':
            return redirect('doctor_dashboard')

        elif user.role == 'PHARMACIST':
            return redirect('pharmacist_dashboard')

    return render(request, 'accounts/home.html')


def register_choice(request):
    """Public role-selection page so registration works without dropdown UI."""
    return render(request, "accounts/register_choice.html")

def live_sales_data(request):
    """Small JSON endpoint used by dashboard widgets for live revenue refresh."""

    today = timezone.now().date()

    revenue = (
        InvoiceItem.objects
        .filter(invoice__created_at__date=today)
        .aggregate(total=Sum("total_with_tax"))
    )["total"] or 0

    return JsonResponse({
        "today_revenue": float(revenue)
    })

User = get_user_model()


@login_required
def admin_dashboard(request):
    """Admin dashboard summarizing approvals, stock health, and business analytics."""

    today = timezone.now().date()
    system_settings = SystemSetting.get_solo()

    # Inventory alerts are created here so the admin dashboard acts as the
    # control center for low-stock, near-expiry, and expired medicine warnings.

    low_stock = get_low_stock_medicines()
    near_expiry_batches = get_near_expiry_batches(system_settings.expiry_alert_days)
    expired_batches = get_expired_batches()

    # LOW STOCK ALERTS
    for med in low_stock:

        Notification.objects.get_or_create(
            title=f"Low Stock Alert - {med.name}",
            defaults={
                "message": f"{med.name} stock is low ({med.stock_quantity} left)",
                "notification_type": "WARNING"
            }
        )

    # NEAR EXPIRY ALERTS
    for batch in near_expiry_batches:

        Notification.objects.get_or_create(
            title=f"Near Expiry - {batch.medicine.name}",
            defaults={
                "message": f"{batch.medicine.name} batch {batch.batch_number} expiring soon",
                "notification_type": "WARNING"
            }
        )

    # EXPIRED ALERTS
    for batch in expired_batches:

        Notification.objects.get_or_create(
            title=f"Expired Medicine - {batch.medicine.name}",
            defaults={
                "message": f"{batch.medicine.name} batch {batch.batch_number} expired",
                "notification_type": "CRITICAL"
            }
        )

    ensure_admin(request.user)

    today = timezone.now().date()

    # -------- BASIC COUNTS --------
    total_doctors = User.objects.filter(role="DOCTOR").count()
    total_pharmacists = User.objects.filter(role="PHARMACIST").count()

    total_patients = Patient.objects.count()
    total_medicines = Medicine.objects.count()
    total_suppliers = Supplier.objects.count()
    total_stores = Store.objects.count()

    total_revenue = Invoice.objects.aggregate(
        total=Sum("total_amount")
    )["total"] or 0


    # -------- EXPIRY DATA --------
    near_expiry = Batch.objects.filter(
        expiry_date__lte=today + timezone.timedelta(days=system_settings.expiry_alert_days),
        expiry_date__gte=today
    ).count()

    expired = Batch.objects.filter(
        expiry_date__lt=today
    ).count()


    # -------- ANALYTICS --------
    labels, revenue_values, profit_values = ReportService.monthly_profit_trend(6)

    today_revenue = ReportService.today_revenue()
    today_sales = ReportService.today_sales_count()

    analytics = ReportService.dashboard_analytics()

    recent_invoices = Invoice.objects.order_by("-created_at")[:5]

 

    recent_activity = ActivityLog.objects.select_related("user").order_by("-created_at")[:10]

    # -------- ALERT COUNTS --------

    pending_doctors = User.objects.filter(role="DOCTOR", is_approved=False).count()

    pending_pharmacists = User.objects.filter(role="PHARMACIST", is_approved=False).count()

    low_stock_count = Batch.objects.filter(quantity__lt=10).count()

    near_expiry_count = Batch.objects.filter(
        expiry_date__lte=today + timezone.timedelta(days=system_settings.expiry_alert_days),
        expiry_date__gte=today
    ).count()

    expired_count = Batch.objects.filter(
        expiry_date__lt=today
    ).count()

    low_stock_medicines = get_low_stock_medicines()
    near_expiry_batches = get_near_expiry_batches(system_settings.expiry_alert_days)
    expired_batches = get_expired_batches()

    dead_stock = ReportService.dead_stock()
    fast_moving = ReportService.fast_moving_medicines()

    context = {
        "total_doctors": total_doctors,
        "total_pharmacists": total_pharmacists,
        "total_patients": total_patients,
        "total_medicines": total_medicines,
        "total_suppliers": total_suppliers,
        "total_stores": total_stores,
        "total_revenue": total_revenue,

        "near_expiry": near_expiry,
        "expired": expired,

        "today_revenue": today_revenue,
        "today_sales": today_sales,

        "stock_value": analytics["stock_value"],
        "most_profitable": analytics["most_profitable"],
        "monthly_growth": analytics["monthly_growth"],

        "profit_labels_json": json.dumps(labels),
        "revenue_values_json": json.dumps(revenue_values),
        "profit_values_json": json.dumps(profit_values),

        "recent_invoices": recent_invoices,
        "recent_activity": recent_activity,

        "pending_doctors": pending_doctors,
        "pending_pharmacists": pending_pharmacists,
        "low_stock_count": low_stock_count,
        "near_expiry_count": near_expiry_count,
        "expired_count": expired_count,
        "low_stock_count": low_stock_medicines.count(),
        "near_expiry_count": near_expiry_batches.count(),
        "expired_count": expired_batches.count(),

        "dead_stock": dead_stock,
        "fast_moving": fast_moving,
        "system_settings": system_settings,
    }

    return render(request, "accounts/admin_dashboard.html", context)


@login_required
def system_settings_view(request):
    """Admin screen for simple security and operational configuration."""
    ensure_admin(request.user)

    settings_obj = SystemSetting.get_solo()

    if request.method == "POST":
        form = SystemSettingForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            log_activity(
                request.user,
                "STOCK_UPDATED",
                f"System settings updated by {request.user.full_name}"
            )
            Notification.objects.create(
                title="System Settings Updated",
                message=f"{request.user.full_name} updated registration and alert settings",
                notification_type="INFO"
            )
            return redirect("system_settings")
    else:
        form = SystemSettingForm(instance=settings_obj)

    security_context = {
        "approved_doctors": User.objects.filter(role="DOCTOR", is_approved=True).count(),
        "approved_pharmacists": User.objects.filter(role="PHARMACIST", is_approved=True).count(),
        "pending_doctors": User.objects.filter(role="DOCTOR", is_approved=False).count(),
        "pending_pharmacists": User.objects.filter(role="PHARMACIST", is_approved=False).count(),
        "active_stores": Store.objects.filter(is_active=True).count(),
    }

    return render(
        request,
        "accounts/system_settings.html",
        {
            "form": form,
            "security_context": security_context,
        }
    )


@login_required
def store_management(request):
    """Admin UI for creating stores and reviewing store staffing."""
    ensure_admin(request.user)

    if request.method == "POST":
        form = StoreForm(request.POST)
        if form.is_valid():
            store = form.save()
            log_activity(
                request.user,
                "STOCK_UPDATED",
                f"Store {store.name} was created by {request.user.full_name}"
            )
            Notification.objects.create(
                title="New Store Created",
                message=f"{store.name} is ready for pharmacist assignment",
                notification_type="INFO"
            )
            return redirect("store_management")
    else:
        form = StoreForm()

    stores = Store.objects.select_related("city", "area").prefetch_related("staff").order_by("name")

    search_query = request.GET.get("q", "").strip()
    city_id = request.GET.get("city", "").strip()
    area_id = request.GET.get("area", "").strip()
    status = request.GET.get("status", "").strip()

    if search_query:
        stores = stores.filter(name__icontains=search_query)

    if city_id:
        stores = stores.filter(city_id=city_id)

    if area_id:
        stores = stores.filter(area_id=area_id)

    if status == "active":
        stores = stores.filter(is_active=True)
    elif status == "inactive":
        stores = stores.filter(is_active=False)

    store_rows = [
        {
            "store": store,
            "assignment_form": StoreStaffAssignmentForm(prefix=f"store-{store.id}"),
            "edit_form": StoreForm(instance=store, prefix=f"edit-store-{store.id}"),
        }
        for store in stores
    ]

    context = {
        "form": form,
        "stores": stores,
        "store_rows": store_rows,
        "filter_cities": City.objects.filter(is_active=True).order_by("name"),
        "filter_areas": Area.objects.filter(is_active=True).select_related("city").order_by("city__name", "name"),
        "selected_query": search_query,
        "selected_city": city_id,
        "selected_area": area_id,
        "selected_status": status,
    }
    return render(request, "accounts/store_management.html", context)


@login_required
def edit_store(request, store_id):
    """Update an existing store from the admin store-management page."""
    ensure_admin(request.user)

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    store = get_object_or_404(Store, pk=store_id)
    form = StoreForm(request.POST, instance=store, prefix=f"edit-store-{store.id}")

    if form.is_valid():
        updated_store = form.save()
        log_activity(
            request.user,
            "STOCK_UPDATED",
            f"Store {updated_store.name} was updated by {request.user.full_name}"
        )
        Notification.objects.create(
            title="Store Updated",
            message=f"{updated_store.name} details were updated",
            notification_type="INFO"
        )

    return redirect("store_management")


@login_required
def delete_store(request, store_id):
    """Delete a store after clearing its staff assignments."""
    ensure_admin(request.user)

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    store = get_object_or_404(Store, pk=store_id)
    store_name = store.name
    store.staff.clear()
    store.delete()

    log_activity(
        request.user,
        "STOCK_UPDATED",
        f"Store {store_name} was deleted by {request.user.full_name}"
    )
    Notification.objects.create(
        title="Store Deleted",
        message=f"{store_name} was removed from store management",
        notification_type="WARNING"
    )

    return redirect("store_management")


@login_required
def assign_store_staff(request, store_id):
    """Attach an approved pharmacist to a specific store."""
    ensure_admin(request.user)

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    store = get_object_or_404(Store, pk=store_id)
    form = StoreStaffAssignmentForm(request.POST, prefix=f"store-{store.id}")

    if form.is_valid():
        pharmacist = form.cleaned_data["pharmacist"]
        store.staff.add(pharmacist)
        log_activity(
            request.user,
            "STOCK_UPDATED",
            f"{pharmacist.full_name} assigned to store {store.name}"
        )
        Notification.objects.create(
            title="Pharmacist Assigned",
            message=f"{pharmacist.full_name} was assigned to {store.name}",
            notification_type="INFO"
        )

    return redirect("store_management")


@login_required
def remove_store_staff(request, store_id, user_id):
    """Detach a pharmacist from a store."""
    ensure_admin(request.user)

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    store = get_object_or_404(Store, pk=store_id)
    pharmacist = get_object_or_404(User, pk=user_id, role="PHARMACIST")
    store.staff.remove(pharmacist)

    log_activity(
        request.user,
        "STOCK_UPDATED",
        f"{pharmacist.full_name} was removed from store {store.name}"
    )
    Notification.objects.create(
        title="Pharmacist Removed",
        message=f"{pharmacist.full_name} was removed from {store.name}",
        notification_type="INFO"
    )

    return redirect("store_management")


@login_required
def procurement_management(request):
    """Admin UI for recording procured medicine batches into store inventory."""
    ensure_admin(request.user)

    if request.method == "POST":
        form = BatchProcurementForm(request.POST)
        if form.is_valid():
            try:
                batch = form.save()
            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    for field_name, messages in exc.message_dict.items():
                        if field_name in form.fields:
                            for message in messages:
                                form.add_error(field_name, message)
                        else:
                            for message in messages:
                                form.add_error(None, message)
                else:
                    for message in exc.messages:
                        form.add_error(None, message)
            else:
                log_activity(
                    request.user,
                    "STOCK_UPDATED",
                    f"Batch {batch.batch_number} procured for {batch.store.name}"
                )
                Notification.objects.create(
                    title="Stock Purchased",
                    message=f"{batch.medicine.name} batch {batch.batch_number} added to {batch.store.name}",
                    notification_type="INFO"
                )
                return redirect("procurement_management")
    else:
        form = BatchProcurementForm()

    recent_batches = Batch.objects.select_related("store", "medicine", "supplier").order_by("-created_at")[:10]

    return render(
        request,
        "accounts/procurement_management.html",
        {
            "form": form,
            "recent_batches": recent_batches,
        }
    )


@login_required
def approve_doctors(request):
    """List doctor accounts waiting for admin approval."""

    if request.user.role != "ADMIN":
        raise PermissionDenied()

    doctors = User.objects.filter(role="DOCTOR", approval_status="PENDING")

    return render(request, "accounts/approve_doctors.html", {
        "doctors": doctors
    })


@login_required
def approve_pharmacists(request):
    """List pharmacist accounts waiting for admin approval."""

    if request.user.role != "ADMIN":
        raise PermissionDenied()

    pharmacists = User.objects.filter(role="PHARMACIST", approval_status="PENDING")

    return render(request, "accounts/approve_pharmacists.html", {
        "pharmacists": pharmacists
    })


@login_required
def approve_user(request, user_id):
    """Approve a doctor or pharmacist after document checks."""

    if request.user.role != "ADMIN":
        raise PermissionDenied("Only admin can approve users.")

    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    user = get_object_or_404(User, id=user_id)

    if user.role == "ADMIN":
        return HttpResponse("Cannot approve admin accounts.")

    if user.is_approved:
        return HttpResponse("User already approved.")

    if not user.license_number:
        return HttpResponse("License number required.")

    if not user.certificate:
        return HttpResponse("Certificate document required.")

    user.is_approved = True
    user.approval_status = "APPROVED"
    user.rejection_reason = ""
    user.rejected_at = None
    user.approved_by = request.user
    user.approved_at = timezone.now()
    user.save(update_fields=["is_approved", "approval_status", "rejection_reason", "rejected_at", "approved_by", "approved_at"])
    from core.models import Notification

    Notification.objects.create(
        title="User Approved",
        message=f"{user.full_name} approved by admin",
        notification_type="INFO"
    )

    log_activity(
        request.user,
        "USER_APPROVED",
        f"{user.full_name} ({user.role}) was approved by {request.user.full_name}"
    )

    messages.success(request, f"{user.full_name} was approved successfully.")

    fallback_route = "approve_doctors" if user.role == "DOCTOR" else "approve_pharmacists"
    return redirect(request.META.get("HTTP_REFERER") or fallback_route)

@login_required
def reject_user(request, user_id):
    """Reject a pending doctor/pharmacist request and log the decision."""

    if request.user.role != "ADMIN":
        raise PermissionDenied()

    if request.method != "POST":
        raise PermissionDenied()

    user = get_object_or_404(User, id=user_id)
    rejection_reason = request.POST.get("rejection_reason", "").strip()

    log_activity(
        request.user,
        "USER_REJECTED",
        f"{user.full_name} ({user.role}) was rejected by {request.user.full_name}"
    )
    user.is_approved = False
    user.approval_status = "REJECTED"
    user.rejection_reason = rejection_reason
    user.rejected_at = timezone.now()
    user.save(update_fields=["is_approved", "approval_status", "rejection_reason", "rejected_at"])

    Notification.objects.create(
        title="Registration Rejected",
        message=f"{user.full_name}'s {user.role.lower()} registration was rejected by admin",
        notification_type="WARNING"
    )

    messages.warning(request, f"{user.full_name} was marked as rejected.")

    fallback_route = "approve_doctors" if user.role == "DOCTOR" else "approve_pharmacists"
    return redirect(request.META.get("HTTP_REFERER") or fallback_route)


def logout_view(request):
    """Log out the current user and return to the public landing page."""
    if request.method != "POST":
        raise PermissionDenied("Invalid request method.")

    logout(request)
    return redirect("home")
