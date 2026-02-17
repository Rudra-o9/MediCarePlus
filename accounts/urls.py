from django.urls import path
from . import views
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from .views import home
from .views import (
    doctor_register,
    pharmacist_register,
    role_redirect,
    doctor_dashboard,
    pharmacist_dashboard,
)

urlpatterns = [
    path('register/doctor/', doctor_register, name='doctor_register'),
    path('register/pharmacist/', pharmacist_register, name='pharmacist_register'),

    # ✅ Proper Login URL
    path('login/', auth_views.LoginView.as_view(
    template_name='registration/login.html'
    ), name='login'),


    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    path('redirect/', role_redirect, name='role_redirect'),

    path('pending/', views.pending_view, name='pending'),

    path('doctor/dashboard/', doctor_dashboard, name='doctor_dashboard'),
    path('pharmacist/dashboard/', pharmacist_dashboard, name='pharmacist_dashboard'),
    path('', views.home, name='home'),
    # path('register/', views.register, name='register'),

    
]
