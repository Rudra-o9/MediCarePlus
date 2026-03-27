"""Service-layer business logic for completing and cancelling invoices.

This is the main file to show when explaining:
- how payment completion deducts stock,
- how FIFO batch usage works,
- how prescription and consultation statuses are recalculated.
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum
from billing.models import InvoiceLog
from pharmacy.models import Batch, StockMovement
from billing.models import InvoiceItemBatch
from django.utils import timezone
from consultations.models import Prescription


class InvoiceService:
    """Single source of truth for invoice payment/cancellation workflow."""

    @staticmethod
    @transaction.atomic
    def process_payment(invoice, performed_by=None):
        """
        Called after a payment is created.
        If invoice becomes fully paid → process it.
        Only approved PHARMACIST can process payment.
        """

        if not performed_by:
            raise ValidationError("User required to process payment.")

        if performed_by.role != "PHARMACIST":
            raise ValidationError("Only pharmacist can process payment.")

        if not performed_by.is_approved:
            raise ValidationError("User is not approved.")

        total_paid = invoice.payments.aggregate(
            total=Sum("amount")
        )["total"] or 0

        if total_paid < invoice.total_amount:
            return

        if invoice.status == "PAID":
            return

        InvoiceService.pay_invoice(invoice, performed_by)

    @staticmethod
    @transaction.atomic
    def pay_invoice(invoice, performed_by=None):
        """
        Deduct stock using FIFO batches (expiry aware)
        and log SALE stock movements.
        """

        if invoice.status == "PAID":
            return invoice

        if not performed_by:
            raise ValidationError("User required to process payment.")

        today = timezone.now().date()
        selected_store = invoice.prescription.assigned_store

        if not selected_store:
            raise ValidationError("Prescription must be assigned to a store before payment processing.")

        # Lock invoice items and candidate batches so concurrent pharmacists
        # cannot double-sell the same stock.
        items = (
            invoice.items
            .select_related("medicine")
            .select_for_update()
        )

        for item in items:
            required_qty = item.quantity

            # FIFO means earlier-expiring batches are sold first, which is the
            # real-world pharmacy rule for reducing expiry waste.
            batches = (
                Batch.objects
                .select_for_update()
                .filter(
                    store=selected_store,
                    medicine=item.medicine,
                    expiry_date__gte=today,
                    quantity__gt=0
                )
                .order_by("expiry_date")
            )

            total_available = sum(b.quantity for b in batches)

            if total_available < required_qty:
                raise ValidationError(
                    f"Not enough non-expired stock for {item.medicine.name}"
                )

            # FIFO Deduction
            for batch in batches:
                if required_qty <= 0:
                    break

                deduct_qty = min(batch.quantity, required_qty)

                # Deduct stock
                batch.quantity -= deduct_qty
                batch.save(update_fields=["quantity"])

                # 🔴 Log SALE movement (negative quantity)
                StockMovement.objects.create(
                    medicine=item.medicine,
                    store=selected_store,
                    batch=batch,
                    movement_type="SALE",
                    quantity=-deduct_qty,
                    reference=invoice.invoice_number,
                    performed_by=performed_by
                )

                # Record batch allocation
                InvoiceItemBatch.objects.create(
                    invoice_item=item,
                    batch=batch,
                    quantity=deduct_qty
                )

                required_qty -= deduct_qty

        # Mark invoice paid
        invoice.status = "PAID"
        invoice.save(update_fields=["status"])

        # Create invoice audit log
        InvoiceLog.objects.create(
            invoice=invoice,
            action="PAID",
            performed_by=performed_by
        )

        # Recalculate prescription + consultation status
        InvoiceService._recalculate_prescription_status(
            invoice.prescription
        )

        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice, performed_by=None):
        """
        Cancel a PAID invoice and restore stock to original batches.
        Only approved PHARMACIST can cancel.
        """

        if not performed_by:
            raise ValidationError("User required to cancel invoice.")

        if performed_by.role != "PHARMACIST":
            raise ValidationError("Only pharmacist can cancel invoice.")

        if not performed_by.is_approved:
            raise ValidationError("User is not approved.")

        if invoice.status != "PAID":
            raise ValidationError("Only PAID invoices can be cancelled.")

        # Lock invoice items and their allocations so stock restoration is safe.
        items = invoice.items.select_for_update()

        for item in items:
            allocations = item.batch_allocations.select_related(
                "batch"
            ).select_for_update()

            for allocation in allocations:
                batch = allocation.batch
                batch.quantity += allocation.quantity
                batch.save(update_fields=["quantity"])

                StockMovement.objects.create(
                    medicine=item.medicine,
                    store=batch.store,
                    batch=batch,
                    movement_type="RETURN",
                    quantity=allocation.quantity,
                    reference=invoice.invoice_number,
                    performed_by=performed_by
                )

            allocations.delete()

        invoice.status = "CANCELLED"
        invoice.save(update_fields=["status"])

        InvoiceLog.objects.create(
            invoice=invoice,
            action="CANCELLED",
            performed_by=performed_by
        )

        InvoiceService._recalculate_prescription_status(
            invoice.prescription
        )

        return invoice


    @staticmethod
    def _recalculate_prescription_status(prescription):
        """Update prescription and consultation status from paid invoice totals."""

        all_items = prescription.items.all()

        any_billed = False
        fully_billed = True

        for p_item in all_items:
            total_billed = (
                p_item.invoice_items
                .filter(invoice__status="PAID")
                .aggregate(total=Sum("quantity"))["total"] or 0
            )

            if total_billed > 0:
                any_billed = True

            if total_billed < p_item.quantity_prescribed:
                fully_billed = False

        if fully_billed:
            prescription.status = "BILLED"
        elif any_billed:
            prescription.status = "PARTIALLY_BILLED"
        else:
            prescription.status = "PENDING"

        has_active_invoice = prescription.invoices.exclude(status="CANCELLED").exists()

        if prescription.status == "BILLED":
            prescription.routing_status = "COMPLETED"
        elif prescription.status == "PARTIALLY_BILLED":
            prescription.routing_status = "PARTIALLY_FULFILLED"
        elif has_active_invoice and prescription.assigned_store_id:
            prescription.routing_status = "RECEIVED"
        elif prescription.assigned_store_id:
            prescription.routing_status = "SENT"
        else:
            prescription.routing_status = "UNSENT"

        prescription.save(update_fields=["status", "routing_status"])

        consultation = prescription.consultation

        if prescription.status == "BILLED":
            consultation.status = "CLOSED"
        else:
            consultation.status = "OPEN"

        consultation.save(update_fields=["status"])
