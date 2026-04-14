"""Fee billing helpers - keep finance rules out of views."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.finance.models import BillingCharge, FeeStructure, Invoice, InvoiceStatus, Payment, PaymentMethod
from apps.students.models import Enrollment


def _invoice_status_for(balance: Decimal) -> str:
    if balance <= Decimal("0"):
        return InvoiceStatus.PAID
    return InvoiceStatus.PARTIAL


def balance_for_enrollment(enrollment_id: int) -> dict:
    """Return charged total, paid total, and balance, preferring invoice records."""
    e = Enrollment.objects.select_related("student").get(pk=enrollment_id)

    inv = getattr(e, "invoice", None)
    if inv:
        paid = inv.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        return {
            "charged": inv.total_amount,
            "paid": paid,
            "balance": inv.balance,
        }

    charged = e.charges.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    paid = e.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    return {
        "charged": charged,
        "paid": paid,
        "balance": charged - paid,
    }


def ensure_invoice_for_enrollment(enrollment: Enrollment) -> Invoice | None:
    """Auto-create invoice from active fee structure when a student enrolls."""
    if hasattr(enrollment, "invoice"):
        return enrollment.invoice

    fs = (
        FeeStructure.objects.filter(program=enrollment.program, is_active=True)
        .order_by("-effective_from")
        .first()
    )
    if not fs:
        return None

    BillingCharge.objects.get_or_create(
        enrollment=enrollment,
        label=fs.name,
        defaults={"amount": fs.total_amount},
    )

    return Invoice.objects.create(
        student=enrollment.student,
        enrollment=enrollment,
        total_amount=fs.total_amount,
        balance=fs.total_amount,
        status=InvoiceStatus.UNPAID,
    )


@transaction.atomic
def record_invoice_payment(
    invoice: Invoice,
    amount: Decimal,
    *,
    method: str = PaymentMethod.MOBILE,
    transaction_code: str = "",
    reference: str = "",
) -> Payment:
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        transaction_code=transaction_code,
        reference=reference,
    )
    paid_total = invoice.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    new_balance = invoice.total_amount - paid_total
    invoice.balance = new_balance if new_balance > Decimal("0") else Decimal("0")
    invoice.status = _invoice_status_for(invoice.balance)
    invoice.save(update_fields=["balance", "status", "updated_at"])
    return payment
