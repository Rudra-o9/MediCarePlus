from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [

    path('register/doctor/', views.doctor_register, name='doctor_register'),
    path('register/pharmacist/', views.pharmacist_register, name='pharmacist_register'),

    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html'
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    path('redirect/', views.role_redirect, name='role_redirect'),
    path('pending/', views.pending_view, name='pending'),

    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('pharmacist/dashboard/', views.pharmacist_dashboard, name='pharmacist_dashboard'),

    path('', views.home, name='home'),

    path('api/live-sales/', views.live_sales_data, name='live_sales_data'),

    # ADMIN DASHBOARD
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("stores/", views.store_management, name="store_management"),
    path("stores/<int:store_id>/edit/", views.edit_store, name="edit_store"),
    path("stores/<int:store_id>/delete/", views.delete_store, name="delete_store"),
    path("stores/<int:store_id>/assign-staff/", views.assign_store_staff, name="assign_store_staff"),
    path("stores/<int:store_id>/remove-staff/<int:user_id>/", views.remove_store_staff, name="remove_store_staff"),
    path("procurement/", views.procurement_management, name="procurement_management"),
    path("system-settings/", views.system_settings_view, name="system_settings"),

    # USER APPROVAL
    path("approve-doctors/", views.approve_doctors, name="approve_doctors"),
    path("approve-pharmacists/", views.approve_pharmacists, name="approve_pharmacists"),
    path("approve/<int:user_id>/", views.approve_user, name="approve_user"),
    path("reject/<int:user_id>/", views.reject_user, name="reject_user"),
]
