import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank / cheque"
    MOBILE = "mobile", "Mobile money"


class FeeStructure(models.Model):
    program = models.ForeignKey(
        "academics.Program",
        on_delete=models.CASCADE,
        related_name="fee_structures",
    )
    name = models.CharField(max_length=255)
    tuition_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    registration_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    other_charges = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["program", "-effective_from"]

    def save(self, *args, **kwargs):
        gross = (self.tuition_fee or Decimal("0")) + (self.registration_fee or Decimal("0")) + (self.other_charges or Decimal("0"))
        discount = self.discount_amount or Decimal("0")
        if discount > gross:
            discount = gross
        self.total_amount = gross - discount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.program.code} - {self.name}"


class BillingCharge(models.Model):
    """Legacy charge records; invoices are primary for API workflows."""

    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="charges",
    )
    label = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.enrollment} - {self.label}"


class InvoiceStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIAL = "partial", "Partially paid"
    PAID = "paid", "Paid"


class Invoice(models.Model):
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    enrollment = models.OneToOneField(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.UNPAID,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"INV-{self.pk} {self.student.admission_number} ({self.status})"


class Payment(models.Model):
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    transaction_code = models.CharField(max_length=100, blank=True, db_index=True)
    receipt_number = models.CharField(max_length=64, unique=True, editable=False)
    paid_on = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=255, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-recorded_at"]

    def save(self, *args, **kwargs):
        if self.invoice and not self.enrollment:
            self.enrollment = self.invoice.enrollment
        if not self.receipt_number:
            self.receipt_number = f"RCP-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.receipt_number} ({self.amount})"


class MpesaCallbackLog(models.Model):
    merchant_request_id = models.CharField(max_length=120, blank=True)
    checkout_request_id = models.CharField(max_length=120, blank=True)
    result_code = models.IntegerField(default=0)
    result_desc = models.CharField(max_length=255, blank=True)
    transaction_code = models.CharField(max_length=120, blank=True, db_index=True)
    phone_number = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    account_reference = models.CharField(max_length=120, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="mpesa_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"MPESA {self.transaction_code or self.checkout_request_id} ({self.result_code})"
