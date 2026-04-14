from django.contrib import admin

from .models import BillingCharge, FeeStructure, Invoice, MpesaCallbackLog, Payment


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = (
        "program",
        "name",
        "tuition_fee",
        "registration_fee",
        "other_charges",
        "discount_amount",
        "total_amount",
        "is_active",
        "effective_from",
    )


@admin.register(BillingCharge)
class BillingChargeAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "label", "amount", "created_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "enrollment", "total_amount", "balance", "status", "updated_at")
    list_filter = ("status",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "invoice", "enrollment", "amount", "method", "transaction_code", "paid_on")
    list_filter = ("method",)


@admin.register(MpesaCallbackLog)
class MpesaCallbackLogAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_code",
        "checkout_request_id",
        "result_code",
        "amount",
        "account_reference",
        "created_at",
    )
    search_fields = ("transaction_code", "checkout_request_id", "account_reference", "phone_number")
