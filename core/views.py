"""Small shared views such as notifications and the simple core dashboard."""

from django.shortcuts import render
from accounts.models import CustomUser
from patients.models import Patient
from pharmacy.models import Medicine, Batch
from billing.models import Invoice
from django.utils import timezone
from django.http import JsonResponse
from .models import Notification
from django.db.models import Sum

def admin_dashboard(request):
    """Legacy core dashboard summary view."""

    doctors = CustomUser.objects.filter(role="DOCTOR").count()
    pharmacists = CustomUser.objects.filter(role="PHARMACIST").count()

    patients = Patient.objects.count()
    medicines = Medicine.objects.count()

    today = timezone.now().date()

    today_sales = Invoice.objects.filter(
        created_at__date=today
    ).aggregate(total=Sum("total_amount"))["total"] or 0

    context = {
        "doctors": doctors,
        "pharmacists": pharmacists,
        "patients": patients,
        "medicines": medicines,
        "today_sales": today_sales,
    }

    return render(request, "core/admin_dashboard.html", context)

def get_notifications(request):
    """Return recent notifications for the dashboard header panel."""

    # Keep the header widget compact by returning only the latest few alerts.
    notifications = Notification.objects.order_by("-created_at")[:4]

    data = []

    for n in notifications:
        data.append({
            "title": n.title,
            "message": n.message,
            "type": n.notification_type,
            "time": n.created_at.strftime("%H:%M")
        })

    return JsonResponse({"notifications": data})
