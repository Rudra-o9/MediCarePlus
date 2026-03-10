from django.urls import path
from .views import (
    ConsultationCreateView,
    ConsultationDetailView,
    AddDiagnosisView,
    AddPrescriptionView,
    consultation_list,
    start_consultation
)

app_name = "consultations"

urlpatterns = [

    path('', consultation_list, name='consultation_list'),

    path('start/<int:patient_id>/', start_consultation, name='start_consultation'),

    path('create/<int:pk>/', ConsultationCreateView.as_view(), name='consultation_create'),

    path('<int:pk>/', ConsultationDetailView.as_view(), name='consultation_detail'),

    path('<int:pk>/add-diagnosis/', AddDiagnosisView.as_view(), name='add_diagnosis'),

    path('<int:pk>/add-prescription/', AddPrescriptionView.as_view(), name='add_prescription'),
]