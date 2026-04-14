from django.urls import path

from .views import (
    ApiLoginView,
    AssessmentCreateView,
    MpesaDarajaCallbackView,
    MpesaPaymentView,
    ResultsView,
    StudentProfileView,
)

urlpatterns = [
    path("login/", ApiLoginView.as_view(), name="api_login"),
    path("student/profile/", StudentProfileView.as_view(), name="api_student_profile"),
    path("results/", ResultsView.as_view(), name="api_results"),
    path("assessments/", AssessmentCreateView.as_view(), name="api_assessments"),
    path("payments/mpesa/", MpesaPaymentView.as_view(), name="api_mpesa_payment"),
    path("payments/mpesa/callback/", MpesaDarajaCallbackView.as_view(), name="api_mpesa_callback"),
]

