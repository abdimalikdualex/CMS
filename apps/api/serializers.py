from decimal import Decimal

from rest_framework import serializers

from apps.assessments.models import AssessmentAttempt, CompetencyGrade
from apps.finance.models import Invoice


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class AssessmentAttemptCreateSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    assessment_id = serializers.IntegerField()
    attempt_number = serializers.IntegerField(required=False, min_value=1)
    grade = serializers.ChoiceField(choices=CompetencyGrade.choices)
    score = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    comments = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        return AssessmentAttempt.objects.create(**validated_data)


class MpesaPaymentSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    phone_number = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    transaction_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        invoice = Invoice.objects.filter(pk=attrs["invoice_id"]).first()
        if not invoice:
            raise serializers.ValidationError("Invoice not found.")
        if attrs["amount"] <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than zero.")
        attrs["invoice"] = invoice
        return attrs


class MpesaCallbackSerializer(serializers.Serializer):
    Body = serializers.DictField()

