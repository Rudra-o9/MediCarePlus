"""Store-side inventory views and pharmacist dashboard."""

from django.shortcuts import get_object_or_404, render, redirect
from .models import Medicine, Batch, StockMovement, Supplier, MedicineCategory
from .forms import MedicineCategoryForm, MedicineForm, SupplierForm
from .services import (
    get_low_stock_medicines,
    get_near_expiry_batches,
    get_expired_batches
)
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
import json
from accounts.services.dashboard_service import DashboardService
from billing.services.report_service import ReportService
from billing.models import Invoice
from consultations.models import Prescription


def get_user_store(user):
    """Return the active store for the currently logged-in pharmacist."""
    return user.stores.filter(is_active=True).first()


def ensure_inventory_access(user):
    """Shared access guard for inventory/report pages."""
    if not user.is_authenticated:
        raise PermissionDenied("Login required.")
    if not user.is_approved:
        raise PermissionDenied("User not approved.")
    if user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")


def ensure_admin_inventory_access(user):
    """Guard for admin-only master-data management pages."""
    ensure_inventory_access(user)
    if user.role != "ADMIN":
        raise PermissionDenied("Admin access required.")


@login_required
def pharmacist_dashboard(request):
    """Main `/pharmacy/dashboard/` pharmacist dashboard with analytics."""
    ensure_inventory_access(request.user)
    period = int(request.GET.get("period", 6))
    current_store = get_user_store(request.user)
    pending_prescription_count = 0
    draft_invoice_count = 0
    paid_invoice_count = 0

    context = DashboardService.pharmacist_dashboard_data()

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
        "stock_value": analytics["stock_value"],
        "has_trend_data": any(json.loads(context["trend_values_json"])),
        "has_top_medicine_data": bool(json.loads(context["top_values_json"])),
        "has_category_data": bool(cat_labels),
        "has_today_top_data": bool(top_today_labels),
        "current_store": current_store,
        "no_store_assigned": current_store is None,
        "pending_prescription_count": pending_prescription_count,
        "draft_invoice_count": draft_invoice_count,
        "paid_invoice_count": paid_invoice_count,
        "user": request.user,
    })
    return render(request, "pharmacy/dashboard.html", context)

@login_required
def low_stock_medicines(request):
    """List medicines currently below or at low-stock threshold."""
    ensure_inventory_access(request.user)
    medicines = list(get_low_stock_medicines())
    out_of_stock_count = sum(1 for med in medicines if (med.stock_quantity or 0) == 0)
    return render(request, "pharmacy/low_stock.html", {
        "medicines": medicines,
        "low_stock_count": len(medicines),
        "out_of_stock_count": out_of_stock_count,
    })

@login_required
def near_expiry_batches(request):
    """List soon-to-expire batches that still have sellable quantity."""
    ensure_inventory_access(request.user)
    batches = list(get_near_expiry_batches())
    total_quantity = sum(batch.quantity for batch in batches)
    return render(request, "pharmacy/near_expiry.html", {
        "batches": batches,
        "batch_count": len(batches),
        "near_expiry_quantity": total_quantity,
        "today": timezone.localdate(),
    })

@login_required
def expired_batches(request):
    """List expired batches to support stock cleanup and admin review."""
    ensure_inventory_access(request.user)
    batches = list(get_expired_batches())
    total_quantity = sum(batch.quantity for batch in batches)
    return render(request, "pharmacy/expired_batches.html", {
        "batches": batches,
        "expired_batch_count": len(batches),
        "expired_quantity": total_quantity,
    })

@login_required
def medicine_list(request):
    """Medicine catalog page for pharmacy-side browsing."""
    ensure_inventory_access(request.user)
    medicines = Medicine.objects.select_related("category").order_by("name")
    active_count = medicines.filter(is_active=True).count()
    low_stock_count = medicines.filter(stock_quantity__lte=F("low_stock_threshold")).count()
    return render(request, "pharmacy/medicine_list.html", {
        "medicines": medicines,
        "medicine_count": medicines.count(),
        "active_count": active_count,
        "low_stock_count": low_stock_count,
    })


@login_required
def manage_categories(request):
    """Admin UI for medicine category master data."""
    ensure_admin_inventory_access(request.user)

    if request.method == "POST":
        form = MedicineCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("manage_categories")
    else:
        form = MedicineCategoryForm()

    categories = MedicineCategory.objects.select_related("parent").order_by("name")
    top_level_count = categories.filter(parent__isnull=True).count()
    child_count = categories.filter(parent__isnull=False).count()
    return render(
        request,
        "pharmacy/manage_categories.html",
        {
            "form": form,
            "categories": categories,
            "category_count": categories.count(),
            "top_level_count": top_level_count,
            "child_count": child_count,
        }
    )


@login_required
def edit_category(request, pk):
    """Admin UI for updating an existing category."""
    ensure_admin_inventory_access(request.user)
    category = get_object_or_404(MedicineCategory, pk=pk)

    if request.method == "POST":
        form = MedicineCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect("manage_categories")
    else:
        form = MedicineCategoryForm(instance=category)

    categories = MedicineCategory.objects.select_related("parent").order_by("name")
    top_level_count = categories.filter(parent__isnull=True).count()
    child_count = categories.filter(parent__isnull=False).count()
    return render(
        request,
        "pharmacy/manage_categories.html",
        {
            "form": form,
            "categories": categories,
            "editing": category,
            "category_count": categories.count(),
            "top_level_count": top_level_count,
            "child_count": child_count,
        }
    )


@login_required
def manage_suppliers(request):
    """Admin UI for supplier master data."""
    ensure_admin_inventory_access(request.user)

    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("manage_suppliers")
    else:
        form = SupplierForm()

    suppliers = Supplier.objects.order_by("name")
    active_count = suppliers.filter(is_active=True).count()
    inactive_count = suppliers.filter(is_active=False).count()
    return render(
        request,
        "pharmacy/manage_suppliers.html",
        {
            "form": form,
            "suppliers": suppliers,
            "supplier_count": suppliers.count(),
            "active_supplier_count": active_count,
            "inactive_supplier_count": inactive_count,
        }
    )


@login_required
def edit_supplier(request, pk):
    """Admin UI for updating supplier details."""
    ensure_admin_inventory_access(request.user)
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            return redirect("manage_suppliers")
    else:
        form = SupplierForm(instance=supplier)

    suppliers = Supplier.objects.order_by("name")
    active_count = suppliers.filter(is_active=True).count()
    inactive_count = suppliers.filter(is_active=False).count()
    return render(
        request,
        "pharmacy/manage_suppliers.html",
        {
            "form": form,
            "suppliers": suppliers,
            "editing": supplier,
            "supplier_count": suppliers.count(),
            "active_supplier_count": active_count,
            "inactive_supplier_count": inactive_count,
        }
    )


@login_required
def manage_medicines(request):
    """Admin UI for medicine and pricing master data."""
    ensure_admin_inventory_access(request.user)

    if request.method == "POST":
        form = MedicineForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("manage_medicines")
    else:
        form = MedicineForm()

    medicines = Medicine.objects.select_related("category").order_by("name")
    active_count = medicines.filter(is_active=True).count()
    low_stock_count = medicines.filter(stock_quantity__lte=F("low_stock_threshold")).count()
    return render(
        request,
        "pharmacy/manage_medicines.html",
        {
            "form": form,
            "medicines": medicines,
            "medicine_count": medicines.count(),
            "active_medicine_count": active_count,
            "low_stock_medicine_count": low_stock_count,
        }
    )


@login_required
def edit_medicine(request, pk):
    """Admin UI for editing medicine catalog and pricing values."""
    ensure_admin_inventory_access(request.user)
    medicine = get_object_or_404(Medicine, pk=pk)

    if request.method == "POST":
        form = MedicineForm(request.POST, instance=medicine)
        if form.is_valid():
            form.save()
            return redirect("manage_medicines")
    else:
        form = MedicineForm(instance=medicine)

    medicines = Medicine.objects.select_related("category").order_by("name")
    active_count = medicines.filter(is_active=True).count()
    low_stock_count = medicines.filter(stock_quantity__lte=F("low_stock_threshold")).count()
    return render(
        request,
        "pharmacy/manage_medicines.html",
        {
            "form": form,
            "medicines": medicines,
            "editing": medicine,
            "medicine_count": medicines.count(),
            "active_medicine_count": active_count,
            "low_stock_medicine_count": low_stock_count,
        }
    )

@login_required
def supplier_purchase_report(request):
    """Admin/pharmacy report summarizing stock purchased from each supplier."""
    ensure_inventory_access(request.user)
    suppliers = Supplier.objects.all()

    report_data = []

    for supplier in suppliers:
        batches = Batch.objects.filter(supplier=supplier)

        total_quantity = batches.aggregate(
            total=Sum("quantity")
        )["total"] or 0

        total_value = batches.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("purchase_price"),
                    output_field=DecimalField()
                )
            )
        )["total"] or 0

        report_data.append({
            "supplier": supplier,
            "total_batches": batches.count(),
            "total_quantity": total_quantity,
            "total_value": total_value,
        })

    return render(request, "pharmacy/supplier_report.html", {
        "report_data": report_data,
        "supplier_count": len(report_data),
        "total_supplier_quantity": sum(row["total_quantity"] for row in report_data),
        "total_supplier_value": sum(row["total_value"] for row in report_data),
    })  

@login_required
def category_sales_report(request):
    """Sales grouped by medicine category for management reporting."""
    ensure_inventory_access(request.user)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    sales_filter = {'movement_type': 'SALE'}

    if start_date:
        sales_filter['created_at__date__gte'] = start_date
    if end_date:
        sales_filter['created_at__date__lte'] = end_date

    categories = MedicineCategory.objects.all()
    report_data = []

    for category in categories:
        sales = StockMovement.objects.filter(
            medicine__category=category,
            **sales_filter
        )

        raw_quantity = sales.aggregate(
            total_qty=Sum('quantity')
        )['total_qty'] or 0

        raw_value = sales.aggregate(
            total_val=Sum(
                ExpressionWrapper(
                    F('quantity') * F('medicine__default_selling_price'),
                    output_field=DecimalField()
                )
            )
        )['total_val'] or 0

        # Sale ledger rows are stored as negative outgoing quantities, but the
        # report should present sold quantity and value as positive business metrics.
        total_quantity = abs(raw_quantity)
        total_value = abs(raw_value)

        report_data.append({
            'category': category.name,
            'total_quantity': total_quantity,
            'total_sales_value': total_value,
        })

    return render(request, 'pharmacy/category_report.html', {
        'report_data': report_data,
        'start_date': start_date,
        'end_date': end_date,
        'category_count': len(report_data),
        'total_category_quantity': sum(row['total_quantity'] for row in report_data),
        'total_category_sales_value': sum(row['total_sales_value'] for row in report_data),
    })

@login_required
def doctor_medicine_stock(request):
    """Doctor-facing stock visibility page used before routing prescriptions."""

    if request.user.role != "DOCTOR":
        raise PermissionDenied("Doctors only.")

    medicines = Medicine.objects.all()

    today = timezone.now().date()

    stock_data = []

    for med in medicines:

        total_stock = med.batches.aggregate(
            total=Sum("quantity")
        )["total"] or 0

        near_expiry = med.batches.filter(
            expiry_date__lte=today + timezone.timedelta(days=30),
            expiry_date__gte=today,
            quantity__gt=0
        ).exists()

        stock_data.append({
            "medicine": med,
            "stock": total_stock,
            "low_stock": med.is_low_stock(),
            "near_expiry": near_expiry
        })

    return render(
        request,
        "pharmacy/doctor_medicine_stock.html",
        {
            "stock_data": stock_data,
            "medicine_count": len(stock_data),
            "low_stock_count": sum(1 for item in stock_data if item["low_stock"]),
            "near_expiry_count": sum(1 for item in stock_data if item["near_expiry"]),
        }
    )

@login_required
def expiry_report(request):
    """Operational expiry report for stock planning."""

    ensure_inventory_access(request.user)

    today = timezone.now().date()
    limit = today + timezone.timedelta(days=30)
    urgent_limit = today + timezone.timedelta(days=7)

    batches = Batch.objects.filter(
        expiry_date__gte=today,
        expiry_date__lte=limit,
        quantity__gt=0
    ).select_related("medicine").order_by("expiry_date")

    batch_list = list(batches)

    return render(
        request,
        "pharmacy/expiry_report.html",
        {
            "batches": batch_list,
            "batch_count": len(batch_list),
            "total_quantity": sum(batch.quantity for batch in batch_list),
            "today": today,
            "limit": limit,
            "urgent_limit": urgent_limit,
        }
    )

@login_required
def stock_report(request):
    """Summary of stock quantity, batch count, and inventory value."""

    ensure_inventory_access(request.user)

    medicines = Medicine.objects.all()

    stock_data = []

    for med in medicines:

        batches = med.batches.all()

        total_stock = batches.aggregate(
            total=Sum("quantity")
        )["total"] or 0

        batch_count = batches.count()

        stock_value = sum(
            batch.quantity * batch.purchase_price
            for batch in batches
        )

        stock_data.append({
            "medicine": med,
            "stock": total_stock,
            "batches": batch_count,
            "value": stock_value
        })

    return render(
        request,
        "pharmacy/stock_report.html",
        {
            "stock_data": stock_data,
            "medicine_count": len(stock_data),
            "total_stock_units": sum(item["stock"] for item in stock_data),
            "total_stock_value": sum(item["value"] for item in stock_data),
        }
    )
