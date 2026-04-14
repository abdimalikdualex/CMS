from django.contrib import messages
from django.shortcuts import redirect

from apps.accounts.models import UserType
from apps.assessments.models import AssessmentAttempt, CompetencyGrade
from apps.finance.models import Invoice, InvoiceStatus


class RoleContextMiddleware:
    """Expose user_type on the request for templates and RBAC."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.user_type = getattr(request.user, "user_type", UserType.STUDENT)
            request.is_trainer = request.user_type == UserType.TRAINER
            request.is_finance = request.user_type in {UserType.FINANCE, UserType.ADMISSION_FINANCE}
            request.is_admission = request.user_type in {UserType.ADMISSION, UserType.ADMISSION_FINANCE}
            request.is_parent = request.user_type == UserType.PARENT
            request.is_admin = request.user.is_superuser
            request.pending_assessment_count = 0
            request.unpaid_invoice_count = 0
            try:
                if request.is_admin or getattr(request.user, "can_manage_assessments", False):
                    request.pending_assessment_count = AssessmentAttempt.objects.filter(
                        grade=CompetencyGrade.NOT_YET
                    ).count()
                if request.is_admin or getattr(request.user, "can_manage_finance", False):
                    request.unpaid_invoice_count = Invoice.objects.exclude(status=InvoiceStatus.PAID).count()
            except Exception:
                # Do not block request rendering due to sidebar badge queries.
                request.pending_assessment_count = 0
                request.unpaid_invoice_count = 0
            if not request.user.is_superuser:
                path = request.path or "/"
                protected_prefixes = (
                    "/admin-dashboard/",
                    "/admission-dashboard/",
                    "/admission-finance-dashboard/",
                    "/trainer-dashboard/",
                    "/finance-dashboard/",
                    "/student-dashboard/",
                    "/parent-dashboard/",
                    "/admin/",
                    "/student/",
                )
                role_allowed_prefixes = {
                    UserType.STUDENT: (
                        "/dashboard/",
                        "/student-dashboard/",
                        "/student/",
                        "/logout/",
                    ),
                    UserType.TRAINER: (
                        "/dashboard/",
                        "/trainer-dashboard/",
                        "/admin/courses/",
                        "/admin/programs-courses/",
                        "/admin/cbet/",
                        "/admin/exams/",
                        "/admin/assessments/",
                        "/admin/results/",
                        "/logout/",
                    ),
                    UserType.FINANCE: (
                        "/dashboard/",
                        "/finance-dashboard/",
                        "/admin/finance/",
                        "/admin/reports/",
                        "/logout/",
                    ),
                    UserType.ADMISSION: (
                        "/dashboard/",
                        "/admission-dashboard/",
                        "/admin/admissions/",
                        "/admin/students/",
                        "/logout/",
                    ),
                    UserType.ADMISSION_FINANCE: (
                        "/dashboard/",
                        "/admission-finance-dashboard/",
                        "/admin/admissions/",
                        "/admin/students/",
                        "/admin/finance/",
                        "/admin/reports/",
                        "/logout/",
                    ),
                    UserType.PARENT: (
                        "/dashboard/",
                        "/parent-dashboard/",
                        "/logout/",
                    ),
                }
                if path.startswith(protected_prefixes):
                    allowed_prefixes = role_allowed_prefixes.get(request.user_type, ("/dashboard/", "/logout/"))
                    if not path.startswith(allowed_prefixes):
                        messages.error(request, "Forbidden: You do not have access to that area.")
                        return redirect("dashboard")
        else:
            request.user_type = None
            request.is_trainer = False
            request.is_finance = False
            request.is_admission = False
            request.is_parent = False
            request.is_admin = False
            request.pending_assessment_count = 0
            request.unpaid_invoice_count = 0
        return self.get_response(request)
