# MediCarePlus Viva Notes

This file is a quick explanation guide for faculty discussion.

## 1. Project Idea

MediCarePlus is a role-based medical and pharmacy management system.

- Doctors create consultations and digital prescriptions.
- The system checks nearby pharmacy stores for medicine availability.
- The doctor sends the prescription to the best selected store.
- Pharmacists bill only from their own store stock.
- Admin manages users, stores, procurement, reports, and system settings.

## 2. Main Real-World Features

### Role-based login and approval

What to say:
- The project has three roles: Admin, Doctor, and Pharmacist.
- Doctor and pharmacist registration can require admin approval before access is granted.

Main files:
- `accounts/models.py`
- `accounts/views.py`

### Patient and consultation workflow

What to say:
- Doctors create patients, start consultations, add diagnosis, and create prescriptions.
- Previous treatment history and purchase history are visible while treating the patient.

Main files:
- `patients/models.py`
- `patients/views.py`
- `consultations/views.py`
- `consultations/templates/consultations/consultation_detail.html`

### Prescription routing to stores

What to say:
- Stock belongs to a store, not to an individual pharmacist.
- The system ranks stores by city/area and stock match.
- The doctor manually selects a store from the ranked list.

Main files:
- `pharmacy/models.py`
- `pharmacy/services.py`
- `consultations/views.py`

### Billing and stock deduction

What to say:
- Billing happens against the assigned store only.
- Partial fulfillment is allowed if full stock is not available.
- On payment, stock is deducted using FIFO batches so earlier-expiry stock is used first.

Main files:
- `billing/views.py`
- `billing/models.py`
- `billing/services/invoice_service.py`

### GST billing and reports

What to say:
- GST is captured on invoice items as a sale-time snapshot.
- The system provides sales, profit, and GST summary reports.
- Admin can filter reports store-wise for multi-store management.

Main files:
- `billing/models.py`
- `billing/services/report_service.py`
- `billing/views.py`

### Admin operations and settings

What to say:
- Admin can approve users, create stores, assign pharmacists, procure stock, manage medicine master data, and control system settings.
- Settings include registration access, approval policy, and expiry alert days.

Main files:
- `accounts/views.py`
- `accounts/forms.py`
- `accounts/templates/accounts/system_settings.html`

## 3. Important Business Rules

- Stock belongs to stores.
- Doctors do not send prescriptions to random pharmacies; they choose from ranked nearby stores.
- Pharmacists can bill partially when some medicines are unavailable.
- FIFO stock deduction is used to reduce expiry waste.
- Prescription routing status is tracked as `sent`, `received`, `partially fulfilled`, and `completed`.

## 4. If Faculty Asks “Where Is This Code?”

- Login and role handling: `accounts/views.py`
- User model and roles: `accounts/models.py`
- Doctor consultation logic: `consultations/views.py`
- Store ranking logic: `pharmacy/services.py`
- Billing workflow: `billing/services/invoice_service.py`
- Invoice and GST fields: `billing/models.py`
- Report logic: `billing/services/report_service.py`
- Admin settings: `accounts/views.py`

## 5. Short Viva Summary

MediCarePlus is designed as a real-world clinic and pharmacy coordination system, not just a simple CRUD project. Its main strength is that prescriptions are connected to actual store stock, medicines are billed from real batches, GST is reported properly, and the workflow is separated across doctor, pharmacist, and admin roles.
