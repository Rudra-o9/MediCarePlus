from django.urls import path
from . import views
from .views import (
    PharmacistDashboardView,
    add_payment,
    gst_summary_report_view,
    invoice_detail,
    invoice_list,
    medicine_profit_report_view,
    profit_trend_view,
    invoice_pdf,
    prescription_queue,
    create_invoice
)

app_name = "billing"

urlpatterns = [

    path("dashboard/", PharmacistDashboardView.as_view(), name="pharmacist_dashboard"),

    path("prescriptions/", prescription_queue, name="prescription_queue"),

    path("invoice/create/<int:prescription_id>/", create_invoice, name="create_invoice"),

    path("invoice/<int:pk>/", invoice_detail, name="invoice_detail"),

    path("invoices/", invoice_list, name="invoice_list"),

    path("invoice/<int:invoice_id>/payment/", add_payment, name="add_payment"),

    path("invoice/<int:invoice_id>/pdf/", invoice_pdf, name="invoice_pdf"),

    path("reports/sales/", views.sales_report_view, name="sales_report"),

    path("reports/profit/", medicine_profit_report_view, name="medicine_profit_report"),

    path("reports/gst-summary/", gst_summary_report_view, name="gst_summary_report"),

    path("reports/profit-trend/", profit_trend_view, name="profit_trend"),
]
