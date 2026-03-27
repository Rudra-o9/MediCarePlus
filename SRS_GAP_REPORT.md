# MediCarePlus SRS Gap Report

This document maps the current MediCarePlus implementation against the Software Requirements Specification (SRS) shared for the project.

Purpose:
- help explain the project to faculty,
- show which requirements are already implemented,
- show which requirements are partially implemented,
- identify the most important remaining work for a real-world version.

Status labels used in this report:
- `Done`: feature is implemented and available in the project
- `Partial`: major parts exist, but the feature is not fully polished or complete
- `Missing`: feature is not properly implemented yet

---

## 1. Functional Requirement Status

| SRS Requirement | Status | Current Implementation | Main Files | Remaining Work |
|---|---|---|---|---|
| `R.1 User Authentication` | Done | Role-based login for Admin, Doctor, Pharmacist with approval workflow and dashboard redirect | `accounts/models.py`, `accounts/views.py`, `accounts/urls.py` | Minor polish only |
| `R.2 Medicine Inventory Management` | Done | Store-wise inventory, procurement, and themed admin UI for medicines, categories, suppliers, and pricing exist | `pharmacy/models.py`, `pharmacy/views.py`, `pharmacy/forms.py`, `accounts/views.py` | Minor workflow polish only |
| `R.3 Stock & Expiry Tracking` | Done | Batch stock, low stock, near expiry, expired tracking implemented | `pharmacy/models.py`, `pharmacy/services.py`, `pharmacy/views.py` | Mostly done |
| `R.4 Expiry and Stock Alerts` | Done | Notification-based stock and expiry alerts exist | `accounts/views.py`, `pharmacy/services/inventory_monitor.py`, `core/models.py` | Could be improved with scheduled automation |
| `R.5 GST Billing` | Done | GST is calculated on invoice items and a dedicated GST summary report with CSV export is available | `billing/models.py`, `billing/views.py`, `billing/services/report_service.py`, `billing/tests/test_gst_calculation.py` | Minor reporting polish only |
| `R.6 Patient Record Management` | Done | Patient CRUD, history, purchase history, consultation linkage, and doctor-side previous treatment visibility are implemented | `patients/models.py`, `patients/views.py`, `consultations/views.py` | Minor UX polish only |
| `R.7 Prescription Management` | Done | Doctor creates prescriptions, routes them to stores, pharmacist bills against them, and routing lifecycle states are tracked | `consultations/models.py`, `consultations/views.py`, `billing/views.py`, `billing/services/invoice_service.py` | Minor workflow polish only |
| `R.8 Report Generation` | Done | Sales, profit, GST, stock, expiry, and category reports exist, with store-filtered reporting on key billing reports | `billing/services/report_service.py`, `billing/views.py`, `pharmacy/views.py` | More dashboards can be added later if needed |

---

## 2. SRS User-Wise Feature Status

### 2.1 Pharmacist

| SRS Feature | Status | Notes |
|---|---|---|
| Registration request | Done | Pharmacist registration and admin approval flow exist |
| Manage medicine details | Done | Inventory views are available and admin-facing master data management UI is implemented |
| Perform GST calculation | Done | GST is calculated in invoice items at sale time |
| View prescriptions | Done | Pharmacist sees prescriptions routed to their assigned store |
| Maintain patient purchase records | Done | Purchase history is tied to paid invoices and patient records |

### 2.2 Doctor

| SRS Feature | Status | Notes |
|---|---|---|
| Access patient records | Done | Doctor can view patient and consultation data |
| View patient medicine purchase history | Done | Patient purchase history page exists |
| View pharmacist details and medicine stocks associated with doctor | Done | Doctor can see ranked nearby stores, pharmacist names, contact details, stock match, and missing medicines |
| Upload and manage digital prescriptions | Done | Prescription and prescription item flow is implemented |
| Review previous treatments before prescribing | Done | Previous consultations and recent purchase history are shown in the doctor workflow |

### 2.3 Store Manager / Admin

| SRS Feature | Status | Notes |
|---|---|---|
| Approve/reject doctor and pharmacist registrations | Done | Admin approval pages and actions exist |
| Manage medicine categories, suppliers, and pricing | Done | Themed app UI exists for categories, suppliers, medicines, and pricing management |
| Monitor sales, stock, and expiry reports | Done | Dashboard and reports exist |
| View GST summary reports | Done | Admin and pharmacists can open a GST summary page with date filters and CSV export |
| Control system settings and security access | Done | Admin can manage registration/approval policy and alert settings from the app UI |

---

## 3. Real-World Business Rules Added Beyond the Original Basic SRS

These are important because they make the project stronger for real-world use:

### 3.1 Store-Based Inventory Ownership

Status: `Done`

Implemented idea:
- stock belongs to a `Store`
- pharmacists are assigned to stores
- billing only uses stock from the assigned store

Main files:
- `pharmacy/models.py`
- `billing/views.py`
- `billing/services/invoice_service.py`

### 3.2 Doctor-to-Store Prescription Routing

Status: `Done`

Implemented idea:
- doctor creates prescription
- system ranks stores by city/area and medicine availability
- doctor chooses the store manually
- prescription is sent to that store

Main files:
- `consultations/models.py`
- `consultations/views.py`
- `pharmacy/services.py`

### 3.3 Partial Fulfillment

Status: `Done`

Implemented idea:
- if a store does not have full stock, it can still bill the available quantity
- this matches the real-world rule you described

Main files:
- `billing/views.py`
- `billing/services/invoice_service.py`

### 3.4 FIFO Batch-Based Sale Logic

Status: `Done`

Implemented idea:
- earlier-expiring valid batches are used first
- invoice allocations track which exact batch was used

Main files:
- `billing/services/invoice_service.py`
- `billing/models.py`

---

## 4. Important Remaining Gaps

These are the main items still worth building to better match the SRS and real-world expectations.

### 4.1 Full Admin Master Data UI

Status: `Done`

Implemented:
- themed medicine create/edit/delete pages
- category management pages
- supplier management pages
- pricing management pages

Why it matters:
- this moves day-to-day operations into the main project UI instead of depending on Django admin

### 4.2 GST Summary Reporting

Status: `Done`

Implemented:
- report page for taxable amount
- CGST total
- SGST total
- date-wise filter
- pharmacist store scope
- CSV export support

Why it matters:
- this turns GST billing into a management-friendly tax report instead of only an invoice-level calculation

### 4.3 Richer Doctor View for Previous Treatment and Store Details

Status: `Done`

Implemented:
- previous treatments shown on consultation and prescription pages
- recent purchase history shown to the doctor
- ranked store details include pharmacist names, contact info, stock match, and missing medicines

Why it matters:
- this makes prescribing more informed and much easier to explain in viva

### 4.4 Stronger Routed Prescription Lifecycle

Status: `Done`

Current state:
- `routing_status`, invoice status, and prescription status are all tracked
- routing now moves through:
  - `sent`
  - `received`
  - `partially fulfilled`
  - `completed`

Why it matters:
- this improves traceability and pharmacist/doctor coordination

### 4.5 More Store-Specific Reporting

Status: `Done`

Implemented:
- store-wise sales filtering
- store-wise profit filtering
- store-wise GST summary filtering

Why it matters:
- real-world deployment with multiple stores needs management by store, not only global totals

---

## 5. Suggested Next Development Priority

Recommended implementation order:

1. Polish operational dashboards and exports
2. Add optional deployment/admin conveniences
3. Improve frontend consistency where needed
4. Add more automation like scheduled alerts if required
5. Prepare deployment and presentation material

---

## 6. Viva / Faculty Explanation Summary

If faculty asks, the project can currently be explained like this:

> MediCarePlus is a role-based medical and pharmacy management system where doctors create digital prescriptions, patients are linked to treatment records, and pharmacists manage store-based inventory and billing. The system supports expiry-aware batch stock, GST billing, GST summary reporting, patient purchase history, doctor-side treatment review, store-based prescription routing, and store-filtered reporting. The project has moved beyond a basic academic model by adding real-world store ownership of stock, doctor-to-store prescription routing, partial fulfillment logic, operational routing states, and admin-controlled system settings.

---

## 7. Key Reference Files

Use these files first when explaining the project:

- Authentication and roles:
  - `accounts/models.py`
  - `accounts/views.py`

- Patient and consultation flow:
  - `patients/models.py`
  - `patients/views.py`
  - `consultations/models.py`
  - `consultations/views.py`

- Inventory and stores:
  - `pharmacy/models.py`
  - `pharmacy/services.py`
  - `pharmacy/views.py`

- Billing and reports:
  - `billing/models.py`
  - `billing/services/invoice_service.py`
  - `billing/services/report_service.py`
  - `billing/views.py`

- Project configuration:
  - `config/settings.py`
