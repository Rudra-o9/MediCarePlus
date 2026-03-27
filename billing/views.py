"""Billing and report pages used by pharmacists and admins."""

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.utils.timezone import now
from django.utils.dateparse import parse_date

from django.db.models import Sum, Avg, F, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncMonth

from django.http import HttpResponse
from django.template.loader import get_template

from datetime import date, timedelta
import json
import csv

from xhtml2pdf import pisa

from billing.services.report_service import ReportService
from billing.models import Invoice, InvoiceItemBatch, InvoiceItem, Payment

from consultations.models import Prescription
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from decimal import Decimal
from pharmacy.models import Batch, Store


def get_current_store(user):
    return user.stores.filter(is_active=True).first()


# =========================
# Helper: Last N Months
# =========================
def get_last_n_months(n):
    """Helper for chart screens that need a stable month label sequence."""
    today = now()
    months = []

    year = today.year
    month = today.month

    for _ in range(n):
        months.append(today.replace(year=year, month=month, day=1))

        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return list(reversed(months))


# =========================
# Pharmacist Dashboard
# =========================
class PharmacistDashboardView(TemplateView):
    """Older billing-side pharmacist dashboard view.

    The project currently uses `/pharmacy/dashboard/` as the main pharmacist
    dashboard entry, but this view still powers the billing dashboard route.
    """
    template_name = "billing/pharmacist_dashboard.html"

    def dispatch(self, request, *args, **kwargs):

        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied("Login required.")

        if user.role != "PHARMACIST":
            raise PermissionDenied("Access restricted to pharmacist.")

        if not user.is_approved:
            raise PermissionDenied("User not approved.")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        today = timezone.localdate()

        total_revenue = Invoice.objects.aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        today_revenue = Invoice.objects.filter(
            created_at__date=today
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        monthly_revenue = Invoice.objects.filter(
            created_at__year=today.year,
            created_at__month=today.month
        ).aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        total_invoices = Invoice.objects.count()

        avg_sale = Invoice.objects.aggregate(
            avg=Avg("total_amount")
        )["avg"] or 0

        context.update({
            "total_revenue": total_revenue,
            "today_revenue": today_revenue,
            "monthly_revenue": monthly_revenue,
            "total_invoices": total_invoices,
            "avg_sale": avg_sale,
        })

        context.update(ReportService.pharmacist_dashboard_data())

        labels, revenue_values, profit_values = ReportService.monthly_profit_trend(6)

        context["profit_labels_json"] = json.dumps(labels)
        context["profit_values_json"] = json.dumps(profit_values)

        return context


# =========================
# Sales Report
# =========================
@login_required
def sales_report_view(request):
    """Report page showing paid invoices and top-selling medicines."""
    if request.user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")

    invoices = Invoice.objects.filter(status="PAID").order_by("-created_at")
    stores = Store.objects.filter(is_active=True).order_by("city__name", "name")
    selected_store = None
    selected_store_id = request.GET.get("store")
    no_store_assigned = False

    if request.user.role == "PHARMACIST":
        current_store = get_current_store(request.user)
        if not current_store:
            no_store_assigned = True
            invoices = Invoice.objects.none()
        else:
            invoices = invoices.filter(prescription__assigned_store=current_store)
            selected_store = current_store
    elif selected_store_id:
        selected_store = get_object_or_404(Store, pk=selected_store_id, is_active=True)
        invoices = invoices.filter(prescription__assigned_store=selected_store)

    total_invoices = invoices.count()

    avg_sale = invoices.aggregate(
        avg=Avg("total_amount")
    )["avg"] or 0

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if start_date and end_date:

        start = parse_date(start_date)
        end = parse_date(end_date)

        if start and end:

            invoices = invoices.filter(
                created_at__date__gte=start,
                created_at__date__lte=end
            )

    filtered_total = invoices.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    context = {
        "invoices": invoices,
        "total_revenue": filtered_total,
        "today_revenue": ReportService.today_revenue(),
        "monthly_revenue": ReportService.monthly_revenue(),
        "top_medicines": ReportService.top_selling_medicines(store=selected_store),
        "total_invoices": total_invoices,
        "avg_sale": avg_sale,
        "stores": stores,
        "selected_store": selected_store,
        "selected_store_id": str(selected_store.id) if selected_store else "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "no_store_assigned": no_store_assigned,
    }

    return render(request, "billing/sales_report.html", context)


# =========================
# Medicine Profit Report
# =========================
@login_required
def medicine_profit_report_view(request):
    """Profit report screen with optional CSV export."""
    if request.user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")

    today = timezone.localdate()

    start_date = today.replace(day=1)
    end_date = today

    if request.GET.get("start_date"):
        start_date = parse_date(request.GET.get("start_date"))

    if request.GET.get("end_date"):
        end_date = parse_date(request.GET.get("end_date"))

    stores = Store.objects.filter(is_active=True).order_by("city__name", "name")
    selected_store = None
    selected_store_id = request.GET.get("store")

    if request.user.role == "PHARMACIST":
        selected_store = get_current_store(request.user)
        if not selected_store:
            raise PermissionDenied("No active store assigned to this pharmacist.")
    elif selected_store_id:
        selected_store = get_object_or_404(Store, pk=selected_store_id, is_active=True)

    report, summary = ReportService.medicine_profit_report(
        start_date=start_date,
        end_date=end_date,
        store=selected_store,
    )

    if request.GET.get("export") == "csv":

        response = HttpResponse(content_type="text/csv")

        response["Content-Disposition"] = 'attachment; filename="medicine_profit_report.csv"'

        writer = csv.writer(response)

        writer.writerow([
            "Medicine",
            "Quantity Sold",
            "Total Revenue",
            "Total Cost",
            "Total Profit",
            "Profit Margin %"
        ])

        for row in report:

            writer.writerow([
                row["medicine"],
                row["quantity_sold"],
                row["revenue"],
                row["cost"],
                row["profit"],
                row["margin"]
            ])

        return response

    return render(request, "billing/medicine_profit_report.html", {
        "report": report,
        "summary": summary,
        "start_date": start_date,
        "end_date": end_date,
        "stores": stores,
        "selected_store": selected_store,
        "selected_store_id": str(selected_store.id) if selected_store else "",
    })


@login_required
def gst_summary_report_view(request):
    """GST summary report for admin and pharmacist reporting.

    This gives a tax-focused view of paid sales so the project can demonstrate
    GST-compliant billing beyond simple invoice generation.
    """
    if request.user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")

    today = timezone.localdate()
    start_date = today.replace(day=1)
    end_date = today

    if request.GET.get("start_date"):
        start_date = parse_date(request.GET.get("start_date"))
    if request.GET.get("end_date"):
        end_date = parse_date(request.GET.get("end_date"))

    store = None
    stores = Store.objects.filter(is_active=True).order_by("city__name", "name")
    selected_store_id = request.GET.get("store")
    if request.user.role == "PHARMACIST":
        store = get_current_store(request.user)
        if not store:
            raise PermissionDenied("No active store assigned to this pharmacist.")
    elif selected_store_id:
        store = get_object_or_404(Store, pk=selected_store_id, is_active=True)

    raw_rows, summary = ReportService.gst_summary(
        start_date=start_date,
        end_date=end_date,
        store=store,
    )

    rows = []
    for row in raw_rows:
        cgst_total = row["cgst_total"] or Decimal("0.00")
        sgst_total = row["sgst_total"] or Decimal("0.00")
        rows.append({
            "medicine_name": row["medicine__name"],
            "hsn_code": row["medicine__hsn_code"] or "",
            "gst_percentage": row["gst_percentage_at_sale"],
            "quantity_sold": row["quantity_sold"],
            "taxable_value": row["taxable_value"],
            "cgst_total": cgst_total,
            "sgst_total": sgst_total,
            "total_gst": cgst_total + sgst_total,
            "gross_total": row["gross_total"],
        })

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="gst_summary_report.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Medicine",
            "HSN Code",
            "GST %",
            "Quantity Sold",
            "Taxable Value",
            "CGST",
            "SGST",
            "Total GST",
            "Gross Total",
        ])

        for row in rows:
            writer.writerow([
                row["medicine_name"],
                row["hsn_code"],
                row["gst_percentage"],
                row["quantity_sold"],
                row["taxable_value"],
                row["cgst_total"],
                row["sgst_total"],
                row["total_gst"],
                row["gross_total"],
            ])

        return response

    return render(
        request,
        "billing/gst_summary_report.html",
        {
            "rows": rows,
            "summary": summary,
            "start_date": start_date,
            "end_date": end_date,
            "report_store": store,
            "stores": stores,
            "selected_store_id": str(store.id) if store else "",
        }
    )


# =========================
# Profit Trend Page
# =========================
@login_required
def profit_trend_view(request):
    """Detailed monthly profit/revenue trend page."""
    if request.user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")

    period = int(request.GET.get("period", "6"))

    months = get_last_n_months(period)

    profit_expression = ExpressionWrapper(
        (F("invoice_item__price_at_sale") - F("batch__purchase_price")) * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    data = (
        InvoiceItemBatch.objects
        .filter(
            invoice_item__invoice__status="PAID",
            invoice_item__invoice__created_at__gte=months[0]
        )
        .annotate(month=TruncMonth("invoice_item__invoice__created_at"))
        .annotate(profit=profit_expression)
        .values("month")
        .annotate(total_profit=Sum("profit"))
        .order_by("month")
    )

    revenue_data = (
        Invoice.objects
        .filter(status="PAID", created_at__gte=months[0])
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total_revenue=Sum("total_amount"))
        .order_by("month")
    )

    profit_dict = {}

    for entry in data:
        key = entry['month'].strftime('%Y-%m')
        profit_dict[key] = float(entry['total_profit'] or 0)

    revenue_dict = {}

    for entry in revenue_data:
        key = entry["month"].strftime("%Y-%m")
        revenue_dict[key] = float(entry["total_revenue"] or 0)

    labels = []
    profit_values = []
    revenue_values = []

    for month in months:

        key = month.strftime("%Y-%m")

        labels.append(month.strftime("%b %Y"))

        profit_values.append(profit_dict.get(key, 0))

        revenue_values.append(revenue_dict.get(key, 0))

    context = {
        "labels": json.dumps(labels),
        "profit_values": json.dumps(profit_values),
        "revenue_values": json.dumps(revenue_values),
        "selected_period": period
    }

    return render(request, 'billing/profit_trend.html', context)


# =========================
# Invoice PDF
# =========================
@login_required
def invoice_pdf(request, invoice_id):
    """Generate PDF output for a single invoice."""
    if request.user.role not in ["ADMIN", "PHARMACIST"]:
        raise PermissionDenied("Access restricted.")

    invoice = get_object_or_404(Invoice, id=invoice_id)

    if request.user.role == "PHARMACIST":
        current_store = get_current_store(request.user)
        if not current_store or invoice.prescription.assigned_store_id != current_store.id:
            raise PermissionDenied("This invoice does not belong to your store.")

    invoice_items = InvoiceItemBatch.objects.select_related(
        "invoice_item__medicine",
        "batch"
    ).filter(invoice_item__invoice=invoice)

    payments = invoice.payments.all()

    template = get_template("billing/invoice_pdf.html")

    html = template.render({
        "invoice": invoice,
        "invoice_items": invoice_items,
        "payments": payments
    })

    response = HttpResponse(content_type="application/pdf")

    response["Content-Disposition"] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'

    pisa.CreatePDF(html, dest=response)

    return response


# =========================
# Prescription Queue
# =========================
@login_required
def prescription_queue(request):
    """Show prescriptions routed to the pharmacist's current store."""

    if request.user.role != "PHARMACIST":
        raise PermissionDenied("Pharmacists only.")

    current_store = get_current_store(request.user)
    if not current_store:
        return render(
            request,
            "billing/prescription_queue.html",
            {
                "prescriptions": Prescription.objects.none(),
                "no_store_assigned": True,
                "current_store": None,
            }
        )

    prescriptions = Prescription.objects.filter(
        status__in=["PENDING", "PARTIALLY_BILLED"]
    ).filter(
        assigned_store=current_store,
        routing_status__in=["SENT", "RECEIVED", "PARTIALLY_FULFILLED"]
    ).select_related(
        "consultation",
        "consultation__patient",
        "consultation__doctor",
        "assigned_store"
    )

    return render(
        request,
        "billing/prescription_queue.html",
        {
            "prescriptions": prescriptions,
            "no_store_assigned": False,
            "current_store": current_store,
        }
    )


# =========================
# Create Invoice
# =========================
@login_required
def create_invoice(request, prescription_id):
    """Build an invoice using only stock available in the assigned store.

    Partial billing is allowed when the store cannot fulfill every prescribed
    quantity, which matches the real-world rule you described.
    """

    if request.user.role != "PHARMACIST":
        raise PermissionDenied("Pharmacists only.")

    prescription = get_object_or_404(Prescription, pk=prescription_id)
    current_store = get_current_store(request.user)

    if not current_store:
        raise PermissionDenied("No active store assigned to this pharmacist.")

    if prescription.assigned_store_id != current_store.id:
        raise PermissionDenied("This prescription was not assigned to your store.")

    invoice = Invoice.objects.create(
        prescription=prescription
    )

    added_items = 0

    for item in prescription.items.all():

        already_dispensed = (
            InvoiceItem.objects
            .filter(
                prescription_item=item,
                invoice__status="PAID"
            )
            .aggregate(total=Sum("quantity"))["total"] or 0
        )

        remaining = item.quantity_prescribed - already_dispensed

        if remaining <= 0:
            continue

        medicine = item.medicine

        # Only stock from the assigned store is considered valid for billing.
        available_qty = (
            Batch.objects.filter(
                store=current_store,
                medicine=medicine,
                expiry_date__gte=timezone.now().date(),
                quantity__gt=0
            ).aggregate(total=Sum("quantity"))["total"] or 0
        )

        if available_qty <= 0:
            continue

        dispense_qty = min(remaining, available_qty)

        batch = Batch.objects.filter(
            store=current_store,
            medicine=medicine,
            expiry_date__gte=timezone.now().date(),
            quantity__gt=0
        ).order_by("expiry_date").first()

        if not batch:
            continue

        InvoiceItem.objects.create(
            invoice=invoice,
            prescription_item=item,
            quantity=dispense_qty,
            price_at_sale=medicine.default_selling_price
        )
        added_items += 1

    if not added_items:
        invoice.delete()
        messages.error(request, "No billable medicine is available in your store for this prescription.")
        return redirect("billing:prescription_queue")

    invoice.calculate_total()

    if prescription.routing_status == "SENT":
        prescription.routing_status = "RECEIVED"
        prescription.save(update_fields=["routing_status"])

    return redirect("billing:invoice_detail", invoice.pk)


# =========================
# Invoice Detail
# =========================
@login_required
def invoice_detail(request, pk):
    """Invoice detail page scoped to the pharmacist's store."""

    if request.user.role != "PHARMACIST":
        raise PermissionDenied("Pharmacists only.")

    invoice = get_object_or_404(Invoice, pk=pk)

    current_store = get_current_store(request.user)
    if not current_store or invoice.prescription.assigned_store_id != current_store.id:
        raise PermissionDenied("This invoice does not belong to your store.")

    payment_total = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    balance_due = max(invoice.total_amount - payment_total, Decimal("0.00"))

    return render(
        request,
        "billing/invoice_detail.html",
        {
            "invoice": invoice,
            "current_store": current_store,
            "item_count": invoice.items.count(),
            "batch_line_count": InvoiceItemBatch.objects.filter(invoice_item__invoice=invoice).count(),
            "payment_total": payment_total,
            "balance_due": balance_due,
        }
    )


# =========================
# Invoice List
# =========================
@login_required
def invoice_list(request):
    """Invoice list page with search and status filters."""

    if request.user.role != "PHARMACIST":
        raise PermissionDenied("Pharmacists only.")

    invoices = Invoice.objects.select_related(
        "prescription",
        "prescription__consultation__patient",
        "prescription__assigned_store"
    )

    current_store = get_current_store(request.user)
    if not current_store:
        return render(
            request,
            "billing/invoice_list.html",
            {
                "invoices": Invoice.objects.none(),
                "paid_count": 0,
                "draft_count": 0,
                "invoice_total": Decimal("0.00"),
                "result_count": 0,
                "active_status": "",
                "search_query": "",
                "no_store_assigned": True,
                "current_store": None,
            }
        )

    invoices = invoices.filter(
        prescription__assigned_store=current_store
    )

    query = request.GET.get("q")
    status = request.GET.get("status")

    if query:
        invoices = invoices.filter(
            prescription__consultation__patient__full_name__icontains=query
        )

    if status:
        invoices = invoices.filter(status=status)

    invoices = invoices.order_by("-created_at")
    paid_count = invoices.filter(status="PAID").count()
    draft_count = invoices.filter(status="DRAFT").count()
    total_amount = invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

    return render(
        request,
        "billing/invoice_list.html",
        {
            "invoices": invoices,
            "paid_count": paid_count,
            "draft_count": draft_count,
            "invoice_total": total_amount,
            "result_count": invoices.count(),
            "active_status": status or "",
            "search_query": query or "",
            "no_store_assigned": False,
            "current_store": current_store,
        }
    )


# =========================
# Add Payment
# =========================
@login_required
def add_payment(request, invoice_id):
    """Create a payment and then hand off completion to the service layer."""

    if request.user.role != "PHARMACIST":
        raise PermissionDenied("Pharmacists only.")

    invoice = get_object_or_404(Invoice, pk=invoice_id)
    current_store = get_current_store(request.user)
    if not current_store or invoice.prescription.assigned_store_id != current_store.id:
        raise PermissionDenied("This invoice does not belong to your store.")

    if request.method == "POST":

        amount = Decimal(request.POST.get("amount"))
        method = request.POST.get("method")

        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            method=method,
            received_by=request.user
        )

        from billing.services.invoice_service import InvoiceService

        InvoiceService.process_payment(invoice, performed_by=request.user)

        return redirect("billing:invoice_detail", invoice.pk)

    return render(
        request,
        "billing/add_payment.html",
        {"invoice": invoice}
    )
