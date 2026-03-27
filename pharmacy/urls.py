from django.urls import path
from . import views

urlpatterns = [

    # PHARMACIST DASHBOARD
    path("dashboard/", views.pharmacist_dashboard, name="pharmacist_dashboard"),

    # MEDICINE INVENTORY
    path("medicines/", views.medicine_list, name="medicine_list"),
    path("manage/categories/", views.manage_categories, name="manage_categories"),
    path("manage/categories/<int:pk>/edit/", views.edit_category, name="edit_category"),
    path("manage/suppliers/", views.manage_suppliers, name="manage_suppliers"),
    path("manage/suppliers/<int:pk>/edit/", views.edit_supplier, name="edit_supplier"),
    path("manage/medicines/", views.manage_medicines, name="manage_medicines"),
    path("manage/medicines/<int:pk>/edit/", views.edit_medicine, name="edit_medicine"),
    path("low-stock/", views.low_stock_medicines, name="low_stock_medicines"),
    path("near-expiry/", views.near_expiry_batches, name="near_expiry_batches"),
    path("expired-batches/", views.expired_batches, name="expired_batches"),

    # REPORTS
    path("reports/expiry/", views.expiry_report, name="expiry_report"),
    path("reports/stock/", views.stock_report, name="stock_report"),
    path("reports/category-sales/", views.category_sales_report, name="category_sales_report"),
    path("reports/supplier-purchases/", views.supplier_purchase_report, name="supplier_purchase_report"),

    # DOCTOR TOOLS
    path("doctor/medicine-stock/", views.doctor_medicine_stock, name="doctor_medicine_stock"),
]
