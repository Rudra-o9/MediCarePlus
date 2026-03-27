"""Inventory helper functions and store-ranking logic."""

from django.utils import timezone
from datetime import date, timedelta
from django.db.models import F, Sum
from .models import Batch, Medicine, Store


def get_low_stock_medicines():
    """Medicines whose stored stock summary is at or below threshold."""
    return Medicine.objects.filter(
        stock_quantity__lte=F('low_stock_threshold'),
        is_active=True
    )

def get_near_expiry_batches(days=30):
    """Batches that are still sellable but close to expiry."""
    today = timezone.now().date()
    future_date = today + timedelta(days=days)
    return Batch.objects.filter(
        expiry_date__range=(today, future_date),
        quantity__gt=0
    )

def get_expired_batches():
    """Batches that should no longer be sold."""
    today = timezone.now().date()
    return Batch.objects.filter(
        expiry_date__lt=today,
        quantity__gt=0
    )


def rank_stores_for_prescription(prescription):
    """Return a doctor-friendly ranked list of nearby stores for a prescription.

    Ranking strategy:
- prefer stores with full prescription coverage,
- prefer stores in the same area,
- then prefer more matched items and more available units.
    """
    today = timezone.now().date()
    patient = prescription.consultation.patient
    target_city = patient.city or prescription.consultation.doctor.city
    target_area = patient.area or getattr(prescription.consultation.doctor, "area", None)

    if not target_city:
        return []

    stores = Store.objects.filter(
        city=target_city,
        is_active=True
    ).prefetch_related("staff")

    items = list(
        prescription.items.select_related("medicine").all()
    )

    rankings = []

    for store in stores:
        available_count = 0
        partial_count = 0
        total_requested = 0
        total_available_units = 0
        matched_lines = []
        partial_lines = []
        missing_lines = []

        for item in items:
            requested_qty = item.quantity_prescribed
            total_requested += requested_qty

            available_qty = (
                Batch.objects.filter(
                    store=store,
                    medicine=item.medicine,
                    expiry_date__gte=today,
                    quantity__gt=0
                ).aggregate(total=Sum("quantity"))["total"] or 0
            )

            total_available_units += min(available_qty, requested_qty)

            if available_qty >= requested_qty:
                available_count += 1
                matched_lines.append(
                    f"{item.medicine.name} ({requested_qty}/{requested_qty})"
                )
            elif available_qty > 0:
                partial_count += 1
                partial_lines.append(
                    f"{item.medicine.name} ({available_qty}/{requested_qty})"
                )
                missing_lines.append(
                    f"{item.medicine.name} ({requested_qty - available_qty} short)"
                )
            else:
                missing_lines.append(
                    f"{item.medicine.name} ({requested_qty} short)"
                )

        rankings.append({
            "store": store,
            "matched_items": available_count,
            "partial_items": partial_count,
            "total_items": len(items),
            "available_units": total_available_units,
            "requested_units": total_requested,
            "is_full_match": available_count == len(items) and bool(items),
            "same_area": bool(target_area and store.area_id == target_area.id),
            "matched_lines": matched_lines,
            "partial_lines": partial_lines,
            "missing_lines": missing_lines,
            "pharmacist_names": [member.full_name for member in store.staff.all()],
        })

    # Sorted output is what the doctor sees when deciding where to send the prescription.
    rankings.sort(
        key=lambda row: (
            row["is_full_match"],
            row["same_area"],
            row["matched_items"],
            row["available_units"],
        ),
        reverse=True
    )

    return rankings
