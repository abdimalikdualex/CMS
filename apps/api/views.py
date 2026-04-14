from decimal import Decimal

from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserType
from apps.api.serializers import (
    AssessmentAttemptCreateSerializer,
    LoginSerializer,
    MpesaCallbackSerializer,
    MpesaPaymentSerializer,
)
from apps.assessments.models import AssessmentAttempt, Result, StudentUnitResult
from apps.core.services import record_invoice_payment, update_student_result
from apps.finance.models import Invoice, MpesaCallbackLog, Payment, PaymentMethod
from apps.students.models import Student


class ApiLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": "Account is inactive"}, status=status.HTTP_403_FORBIDDEN)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user_type": user.user_type})


class StudentProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.user_type != UserType.STUDENT:
            return Response({"detail": "Students only."}, status=status.HTTP_403_FORBIDDEN)
        student = Student.objects.filter(user=request.user).first()
        if not student:
            return Response({"detail": "Student profile not found."}, status=status.HTTP_404_NOT_FOUND)
        latest_enrollment = student.enrollments.select_related("program", "intake").first()
        return Response(
            {
                "admission_number": student.admission_number,
                "id_number": student.id_number,
                "phone": student.phone,
                "status": student.status,
                "program": latest_enrollment.program.name if latest_enrollment else None,
                "intake": latest_enrollment.intake.label if latest_enrollment else None,
            }
        )


class ResultsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.user_type == UserType.STUDENT:
            student = Student.objects.filter(user=request.user).first()
            if not student:
                return Response([], status=status.HTTP_200_OK)
            rows = Result.objects.filter(student=student).select_related("unit")
            return Response(
                [
                    {
                        "unit_code": r.unit.code,
                        "unit_title": r.unit.title,
                        "final_status": r.final_status,
                        "updated_at": r.updated_at,
                    }
                    for r in rows
                ]
            )

        rows = StudentUnitResult.objects.select_related("enrollment__student", "unit")[:200]
        return Response(
            [
                {
                    "student": r.enrollment.student.admission_number,
                    "unit_code": r.unit.code,
                    "status": r.overall_grade,
                    "publication_status": r.publication_status,
                }
                for r in rows
            ]
        )


class AssessmentCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not (request.user.is_superuser or request.user.user_type == UserType.TRAINER):
            return Response({"detail": "Only staff lecturers can assess."}, status=403)

        serializer = AssessmentAttemptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "attempt_number" not in data:
            last = (
                AssessmentAttempt.objects.filter(
                    enrollment_id=data["enrollment_id"],
                    assessment_id=data["assessment_id"],
                )
                .order_by("-attempt_number")
                .first()
            )
            data["attempt_number"] = (last.attempt_number + 1) if last else 1

        attempt = AssessmentAttempt(
            enrollment_id=data["enrollment_id"],
            assessment_id=data["assessment_id"],
            attempt_number=data["attempt_number"],
            grade=data["grade"],
            comments=data.get("comments", ""),
            score=data.get("score"),
            assessor=request.user,
        )
        attempt.full_clean()
        attempt.save()
        update_student_result(attempt.enrollment.student, attempt.assessment.unit)
        return Response({"id": attempt.id, "attempt_number": attempt.attempt_number}, status=201)


class MpesaPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MpesaPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data["invoice"]
        amount: Decimal = serializer.validated_data["amount"]
        code = serializer.validated_data.get("transaction_code", "")
        phone = serializer.validated_data["phone_number"]

        payment = record_invoice_payment(
            invoice,
            amount,
            method=PaymentMethod.MOBILE,
            transaction_code=code,
            reference=f"STK:{phone}",
        )
        return Response(
            {
                "message": "Payment recorded (M-Pesa callback stub).",
                "receipt_number": payment.receipt_number,
                "invoice_balance": str(invoice.balance),
            },
            status=201,
        )


class MpesaDarajaCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = MpesaCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        body = payload.get("Body", {}) or {}
        callback = body.get("stkCallback", {}) or {}
        result_code = callback.get("ResultCode", -1)
        result_desc = callback.get("ResultDesc", "")
        checkout_request_id = callback.get("CheckoutRequestID", "")
        merchant_request_id = callback.get("MerchantRequestID", "")
        metadata = (callback.get("CallbackMetadata") or {}).get("Item", []) or []
        data = {}
        for item in metadata:
            key = item.get("Name")
            if key:
                data[key] = item.get("Value")

        amount = Decimal(str(data.get("Amount"))) if data.get("Amount") is not None else None
        transaction_code = str(data.get("MpesaReceiptNumber", "") or "")
        phone = str(data.get("PhoneNumber", "") or "")
        account_reference = str(data.get("AccountReference", "") or "")

        payment = None
        if result_code == 0 and amount and transaction_code:
            existing = Payment.objects.filter(transaction_code=transaction_code).select_related("invoice").first()
            if existing:
                payment = existing
            else:
                invoice = None
                ref = account_reference.strip()
                if ref.isdigit():
                    invoice = Invoice.objects.filter(pk=int(ref)).first()
                elif ref.upper().startswith("INV-") and ref[4:].isdigit():
                    invoice = Invoice.objects.filter(pk=int(ref[4:])).first()
                else:
                    invoice = Invoice.objects.filter(student__admission_number__iexact=ref).first()
                if invoice:
                    with transaction.atomic():
                        payment = record_invoice_payment(
                            invoice=invoice,
                            amount=amount,
                            method=PaymentMethod.MOBILE,
                            transaction_code=transaction_code,
                            reference=f"DAR{checkout_request_id}:{phone}",
                        )
        log = MpesaCallbackLog.objects.create(
            merchant_request_id=merchant_request_id,
            checkout_request_id=checkout_request_id,
            result_code=result_code,
            result_desc=result_desc,
            transaction_code=transaction_code,
            phone_number=phone,
            amount=amount,
            account_reference=account_reference,
            raw_payload=payload,
            payment=payment,
        )
        return Response(
            {
                "ResultCode": 0,
                "ResultDesc": "Accepted",
                "log_id": log.pk,
                "payment_id": payment.pk if payment else None,
            },
            status=status.HTTP_200_OK,
        )

