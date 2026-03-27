"""Reporting and analytics queries used by dashboards and report pages."""

from django.db.models import Sum, F
from django.utils import timezone
from django.db.models.functions import TruncMonth
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from billing.models import Invoice, InvoiceItem, InvoiceItemBatch



class ReportService:
    """Central place for revenue, stock, sales, and profit analytics."""

    # =========================
    # BASIC REVENUE REPORTS
    # =========================

    @staticmethod
    def total_revenue():
        """Total paid revenue across all invoices."""
        return (
            Invoice.objects
            .filter(status="PAID")
            .aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

    @staticmethod
    def today_revenue():
        """Revenue for the current business day."""
        today = timezone.localdate()
        start = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        )
        end = start + timedelta(days=1)

        return (
            Invoice.objects
            .filter(
                status="PAID",
                created_at__gte=start,
                created_at__lt=end
            )
            .aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

    @staticmethod
    def today_sales_count():
        """Number of paid invoices for the current day."""
        today = timezone.localdate()
        start = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        )
        end = start + timedelta(days=1)

        return (
            Invoice.objects
            .filter(
                status="PAID",
                created_at__gte=start,
                created_at__lt=end
            )
            .count()
        )

    @staticmethod
    def monthly_revenue():
        """Revenue inside the current calendar month."""
        today = timezone.localdate()
        start = timezone.make_aware(
            timezone.datetime.combine(
                today.replace(day=1),
                timezone.datetime.min.time()
            )
        )
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        end = timezone.make_aware(
            timezone.datetime.combine(
                next_month,
                timezone.datetime.min.time()
            )
        )
        return (
            Invoice.objects
            .filter(
                status="PAID",
                created_at__gte=start,
                created_at__lt=end
            )
            .aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

    @staticmethod
    def last_7_days_revenue():
        """Revenue time series for the last 7 days.

        This uses simple day-by-day windows instead of heavy grouping because it
        is more reliable across MySQL date/time behavior.
        """
        today = timezone.localdate()
        start_date = today - timedelta(days=6)

        labels = []
        values = []

        for i in range(7):
            day = start_date + timedelta(days=i)
            labels.append(day.strftime("%d %b"))
            start = timezone.make_aware(
                timezone.datetime.combine(day, timezone.datetime.min.time())
            )
            end = start + timedelta(days=1)
            total = (
                Invoice.objects
                .filter(
                    status="PAID",
                    created_at__gte=start,
                    created_at__lt=end
                )
                .aggregate(total=Sum("total_amount"))["total"]
                or Decimal("0.00")
            )
            values.append(total)

        return labels, values

    @staticmethod
    def top_selling_medicines(store=None):
        """Most sold medicines based on paid invoice quantities."""
        items = InvoiceItem.objects.filter(invoice__status="PAID")

        if store:
            items = items.filter(invoice__prescription__assigned_store=store)

        return (
            items
            .values("prescription_item__medicine__name")
            .annotate(total_sold=Sum("quantity"))
            .order_by("-total_sold")[:5]
        )

    @staticmethod
    def pharmacist_dashboard_data():
        return {
            "total_revenue": ReportService.total_revenue(),
            "today_revenue": ReportService.today_revenue(),
            "today_sales_count": ReportService.today_sales_count(),
            "monthly_revenue": ReportService.monthly_revenue(),
            "last_7_days": ReportService.last_7_days_revenue(),
            "top_medicines": list(ReportService.top_selling_medicines())
        }

    @staticmethod
    def sales_by_date_range(start_date=None, end_date=None, store=None):
        invoices = Invoice.objects.filter(status="PAID")

        if store:
            invoices = invoices.filter(prescription__assigned_store=store)

        if start_date:
            invoices = invoices.filter(created_at__date__gte=start_date)

        if end_date:
            invoices = invoices.filter(created_at__date__lte=end_date)

        invoices = invoices.order_by("-created_at")

        total_revenue = (
            invoices.aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

        return invoices, total_revenue

    # =========================
    # MEDICINE PROFIT REPORT
    # =========================

    @staticmethod
    def medicine_profit_report(start_date=None, end_date=None, store=None):
        """Per-medicine revenue/cost/profit report from actual batch allocations."""

        allocations = InvoiceItemBatch.objects.filter(
            invoice_item__invoice__status="PAID"
        ).select_related(
            "invoice_item",
            "batch",
            "invoice_item__medicine"
        )

        if store:
            allocations = allocations.filter(
                invoice_item__invoice__prescription__assigned_store=store
            )

        if start_date:
            start_dt = timezone.make_aware(
                timezone.datetime.combine(start_date, timezone.datetime.min.time())
            )
            allocations = allocations.filter(
                invoice_item__invoice__created_at__gte=start_dt
            )

        if end_date:
            end_dt = timezone.make_aware(
                timezone.datetime.combine(end_date, timezone.datetime.min.time())
            ) + timedelta(days=1)
            allocations = allocations.filter(
                invoice_item__invoice__created_at__lt=end_dt
            )

        report = {}

        for allocation in allocations:
            medicine = allocation.invoice_item.medicine
            qty = allocation.quantity

            sale_price = allocation.invoice_item.price_at_sale
            purchase_price = allocation.batch.purchase_price

            revenue = qty * sale_price
            cost = qty * purchase_price
            profit = revenue - cost

            if medicine.id not in report:
                report[medicine.id] = {
                    "medicine": medicine.name,
                    "quantity_sold": 0,
                    "revenue": Decimal("0.00"),
                    "cost": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                    "margin": 0,
                }

            report[medicine.id]["quantity_sold"] += qty
            report[medicine.id]["revenue"] += revenue
            report[medicine.id]["cost"] += cost
            report[medicine.id]["profit"] += profit

        result = list(report.values())

        # Calculate margin and sort
        for item in result:
            if item["revenue"] > 0:
                item["margin"] = round(
                    (item["profit"] / item["revenue"]) * 100, 2
                )
            else:
                item["margin"] = 0

        result.sort(key=lambda x: x["profit"], reverse=True)

        total_revenue = sum(item["revenue"] for item in result)
        total_cost = sum(item["cost"] for item in result)
        total_profit = sum(item["profit"] for item in result)

        if total_revenue > 0:
            total_margin = round((total_profit / total_revenue) * 100, 2)
        else:
            total_margin = 0

        summary = {
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "total_profit": total_profit,
            "total_margin": total_margin,
        }

        return result, summary


    @staticmethod
    def monthly_profit_trend(months=6):
        """Monthly revenue/profit trend used on dashboards."""

        today = datetime.today()
        start_date = today - relativedelta(months=months-1)

        data = (
            InvoiceItemBatch.objects
            .filter(invoice_item__invoice__created_at__date__gte=start_date)
            .annotate(month=TruncMonth("invoice_item__invoice__created_at"))
            .values("month")
            .annotate(
                revenue=Sum("invoice_item__total_with_tax"),
                profit=Sum("invoice_item__subtotal")
            )
            .order_by("month")
        )

        data_dict = {
            d["month"].strftime("%Y-%m"): d
            for d in data
        }

        labels = []
        revenue_values = []
        profit_values = []

        current = start_date.replace(day=1)

        for i in range(months):

            key = current.strftime("%Y-%m")

            labels.append(current.strftime("%b %Y"))

            if key in data_dict:
                revenue_values.append(float(data_dict[key]["revenue"] or 0))
                profit_values.append(float(data_dict[key]["profit"] or 0))
            else:
                revenue_values.append(0)
                profit_values.append(0)

            current += relativedelta(months=1)

        return labels, revenue_values, profit_values

    @staticmethod
    def dashboard_analytics():
        """High-level dashboard KPIs: stock value, top medicine, growth."""

        from billing.models import InvoiceItem
        from pharmacy.models import Batch

        # ----- TOTAL STOCK VALUE -----
        stock_value = Batch.objects.aggregate(
            value=Sum(F("quantity") * F("purchase_price"))
        )["value"] or 0

        # ----- MOST PROFITABLE MEDICINE -----
        top = (
            InvoiceItem.objects
            .values("medicine__name")
            .annotate(profit=Sum("subtotal"))
            .order_by("-profit")
            .first()
        )

        most_profitable = top["medicine__name"] if top else "N/A"


        # ----- MONTHLY GROWTH -----
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.localdate()

        this_month = today.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)

        this_rev = InvoiceItem.objects.filter(
            invoice__created_at__date__gte=this_month
        ).aggregate(total=Sum("total_with_tax"))["total"] or 0


        last_rev = InvoiceItem.objects.filter(
            invoice__created_at__date__gte=last_month,
            invoice__created_at__date__lt=this_month
        ).aggregate(total=Sum("total_with_tax"))["total"] or 0


        growth = 0

        if last_rev > 0:
            growth = ((this_rev - last_rev) / last_rev) * 100


        return {
            "stock_value": round(stock_value, 2),
            "most_profitable": most_profitable,
            "monthly_growth": round(growth, 1)
        }
    
    @staticmethod
    def sales_by_category():
        """Category-wise sales totals."""

        from billing.models import InvoiceItem

        sales = (
            InvoiceItem.objects
            .values("medicine__category__name")
            .annotate(total=Sum("quantity"))
            .order_by("-total")[:5]
        )

        labels = []
        values = []

        for s in sales:
            labels.append(s["medicine__category__name"] or "Other")
            values.append(s["total"])

        return labels, values

    @staticmethod
    def top_medicines_today():
        """Top medicines sold today."""

        from billing.models import InvoiceItem

        today = timezone.localdate()

        sales = (
            InvoiceItem.objects
            .filter(invoice__created_at__date=today)
            .values("medicine__name")
            .annotate(total=Sum("quantity"))
            .order_by("-total")[:5]
        )

        labels = []
        values = []

        for s in sales:
            labels.append(s["medicine__name"])
            values.append(s["total"])

        return labels, values
    
    @staticmethod
    def dead_stock(days=60):
        """Medicines with stock that have not sold within the cutoff period."""

        from pharmacy.models import Medicine
        from billing.models import InvoiceItem
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=days)

        sold_recently = InvoiceItem.objects.filter(
            invoice__status="PAID",
            invoice__created_at__gte=cutoff
        ).values_list("medicine_id", flat=True)

        dead_stock = Medicine.objects.exclude(
            id__in=sold_recently
        ).filter(stock_quantity__gt=0)

        return dead_stock[:5]
    
    @staticmethod
    def fast_moving_medicines():
        """Top-selling medicines across paid invoices."""

        from billing.models import InvoiceItem

        return (
            InvoiceItem.objects
            .filter(invoice__status="PAID")
            .values("medicine__name")
            .annotate(total_sold=Sum("quantity"))
            .order_by("-total_sold")[:5]
        )

    @staticmethod
    def gst_summary(start_date=None, end_date=None, store=None):
        """GST summary report using paid invoice item snapshots."""

        items = InvoiceItem.objects.filter(invoice__status="PAID")

        if start_date:
            start_dt = timezone.make_aware(
                timezone.datetime.combine(start_date, timezone.datetime.min.time())
            )
            items = items.filter(invoice__created_at__gte=start_dt)
        if end_date:
            end_dt = timezone.make_aware(
                timezone.datetime.combine(end_date, timezone.datetime.min.time())
            ) + timedelta(days=1)
            items = items.filter(invoice__created_at__lt=end_dt)
        if store:
            items = items.filter(invoice__prescription__assigned_store=store)

        rows = list(
            items.values(
                "medicine__name",
                "medicine__hsn_code",
                "gst_percentage_at_sale",
            ).annotate(
                quantity_sold=Sum("quantity"),
                taxable_value=Sum("subtotal"),
                cgst_total=Sum("cgst_amount"),
                sgst_total=Sum("sgst_amount"),
                gross_total=Sum("total_with_tax"),
            ).order_by("medicine__name")
        )

        summary = items.aggregate(
            taxable_value=Sum("subtotal"),
            cgst_total=Sum("cgst_amount"),
            sgst_total=Sum("sgst_amount"),
            gross_total=Sum("total_with_tax"),
        )

        taxable_value = summary["taxable_value"] or Decimal("0.00")
        cgst_total = summary["cgst_total"] or Decimal("0.00")
        sgst_total = summary["sgst_total"] or Decimal("0.00")
        gross_total = summary["gross_total"] or Decimal("0.00")

        return rows, {
            "taxable_value": taxable_value,
            "cgst_total": cgst_total,
            "sgst_total": sgst_total,
            "total_gst": cgst_total + sgst_total,
            "gross_total": gross_total,
        }
