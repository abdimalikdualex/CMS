import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, time, timedelta
from io import BytesIO
from io import TextIOWrapper

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.utils import timezone

from apps.academics.models import (
    CourseRegistration,
    Program,
    RegistrationStatus,
    Semester,
    ShortCourse,
    ShortCourseAttendance,
    ShortCourseAssessment,
    ShortCourseCertificate,
    ShortCourseEnrollment,
    ShortCourseEnrollmentStatus,
    ShortCoursePayment,
    ShortCoursePaymentStatus,
    ShortCourseSession,
    Unit,
)
from apps.accounts.models import FinanceProfile, ParentProfile, TrainerProfile, User, UserType
from apps.attachments.models import Placement
from apps.assessments.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentKind,
    CompetencyGrade,
    PublicationStatus,
    Result,
    StudentUnitResult,
)
from apps.core.decorators import (
    admin_required,
    permission_required,
    role_required,
    student_required,
    super_admin_required,
)
from apps.core.forms import (
    AdmissionApplicationForm,
    AssessmentEntryForm,
    AttendanceRecordForm,
    AnnouncementForm,
    BookForm,
    BookIssueForm,
    ClassSessionForm,
    FeeStructureForm,
    InAppNotificationForm,
    CourseRegistrationForm,
    PaymentEntryForm,
    PlacementForm,
    ProgramForm,
    ShortCourseAttendanceForm,
    ShortCourseAssessmentForm,
    ShortCourseCertificateForm,
    ShortCourseEnrollmentForm,
    ShortCoursePaymentForm,
    ShortCourseForm,
    ShortCourseSessionForm,
    StudentAdmissionForm,
    SupervisorEvaluationForm,
    SystemSettingForm,
    UnitForm,
    UnitTrainerAssignmentForm,
    UserCreateForm,
    UserUpdateForm,
)
from apps.core.models import ApprovalStatus, ApprovalTask, ApprovalType, AuditLog, SystemSetting
from apps.core.services.assessment_service import update_student_result
from apps.core.services.finance_service import balance_for_enrollment, record_invoice_payment
from apps.finance.models import FeeStructure, Invoice, InvoiceStatus, MpesaCallbackLog, Payment
from apps.library.models import Book, BookIssue
from apps.students.models import (
    AdmissionApplication,
    ApplicationStatus,
    Enrollment,
    EnrollmentStatus,
    Intake,
    Student,
    StudentDocument,
    StudentDocumentType,
    UnitAssignment,
)
from apps.timetable.models import AttendanceRecord, ClassSession
from apps.communications.models import Announcement, InAppNotification


def home(request):
    """Public landing — single Login CTA."""
    return render(request, "index.html")


def _program_fee_map() -> dict:
    fee_map = {}
    for fs in FeeStructure.objects.filter(is_active=True).order_by("program_id", "-effective_from"):
        if fs.program_id not in fee_map:
            fee_map[fs.program_id] = str(_money_whole(fs.total_amount))
    return fee_map


def _money_whole(value) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def _next_tvet_admission_number() -> str:
    year = timezone.localdate().year
    prefix = f"COL/{year}/"
    existing = (
        Student.objects.filter(admission_number__startswith=prefix)
        .values_list("admission_number", flat=True)
    )
    max_seq = 0
    for adm in existing:
        try:
            seq = int(str(adm).split("/")[-1])
        except Exception:
            continue
        max_seq = max(max_seq, seq)
    return f"{prefix}{max_seq + 1:03d}"


@admin_required
def admin_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    enrollments = ShortCourseEnrollment.objects.select_related("student__user", "short_course")
    if q:
        enrollments = enrollments.filter(
            Q(student__admission_number__icontains=q)
            | Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
            | Q(short_course__name__icontains=q)
            | Q(short_course__course_code__icontains=q)
        )
    recent_enrollments = enrollments.order_by("-enrolled_on")[:8]
    search_results = recent_enrollments[:6] if q else []

    settings_obj = SystemSetting.objects.first()
    total_students = Student.objects.count()
    total_short_courses = ShortCourse.objects.filter(is_active=True).count()
    month_start = timezone.localdate().replace(day=1)
    total_revenue = ShortCoursePayment.objects.filter(paid_on__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0
    enrollments_today = ShortCourseEnrollment.objects.filter(enrolled_on=timezone.localdate()).count()
    pending_assessments = ShortCourseAssessment.objects.filter(outcome=ShortCourseAssessment.Outcome.FAIL).count()
    stats = [
        {
            "title": "Total students",
            "value": total_students,
            "subtitle": "Registered learners",
            "url": "/admin/students/",
        },
        {
            "title": "Active Courses",
            "value": total_short_courses,
            "subtitle": "Short courses running",
            "url": "/admin/courses/",
        },
        {
            "title": "Monthly Revenue",
            "value": total_revenue,
            "subtitle": "Current month collections",
            "url": "/admin/finance/",
        },
        {
            "title": "Enrollments Today",
            "value": enrollments_today,
            "subtitle": "New learners joined today",
            "url": "/admin/students/",
        },
    ]
    actions = [
        {"label": "Add Student", "url": "/admin/students/"},
        {"label": "Enroll Student", "url": "/admin/courses/#short-courses"},
        {"label": "Record Payment", "url": "/admin/finance/"},
        {"label": "Create Course", "url": "/admin/courses/"},
    ]
    activity = [
        {
            "title": f"{e.student.user.get_full_name() or e.student.admission_number} enrolled",
            "meta": f"{e.short_course.course_code} - {e.short_course.name}",
            "status": e.status,
            "when": timezone.make_aware(datetime.combine(e.enrolled_on, time.min)),
        }
        for e in recent_enrollments
    ]
    notifications = []
    if not recent_enrollments:
        notifications.append("No recent enrollments available.")
    pending_fee_count = ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).count()
    if pending_fee_count:
        notifications.append(f"{pending_fee_count} students have pending fees.")
    recent_certificates = (
        ShortCourseCertificate.objects.select_related("enrollment__student", "enrollment__short_course")
        .order_by("-issued_at")[:5]
    )
    recent_payments = ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course").order_by("-recorded_at")[:5]
    recent_assessments = ShortCourseAssessment.objects.select_related(
        "enrollment__student", "enrollment__short_course"
    ).order_by("-assessed_at")[:5]
    for p in recent_payments:
        activity.append(
            {
                "title": f"Payment received {_money_whole(p.amount)}",
                "meta": f"{p.enrollment.student.admission_number} / {p.paid_on}",
                "status": "payment",
                "when": timezone.make_aware(datetime.combine(p.paid_on, time.min)),
            }
        )
    for a in recent_assessments:
        activity.append(
            {
                "title": f"Practical assessment {a.enrollment.short_course.name} - {a.enrollment.student.admission_number}",
                "meta": f"{a.assessed_at:%Y-%m-%d %H:%M}",
                "status": a.outcome or "pending",
                "when": a.assessed_at,
            }
        )
    for r in recent_certificates:
        activity.append(
            {
                "title": f"Certificate issued - {r.enrollment.student.admission_number}",
                "meta": f"{r.enrollment.short_course.name} / {r.issued_at:%Y-%m-%d %H:%M}",
                "status": "issued",
                "when": r.issued_at,
            }
        )
    activity = sorted(activity, key=lambda x: x.get("when") or timezone.now(), reverse=True)[:10]
    course_performance = (
        ShortCourseEnrollment.objects.values("short_course__name")
        .annotate(learners=Count("id"), completed=Count("id", filter=Q(status=ShortCourseEnrollmentStatus.COMPLETED)))
        .order_by("-learners", "short_course__name")[:8]
    )
    return render(
        request,
        "dashboard/admin_dashboard.html",
        {
            "page_title": "Administration",
            "stats": stats,
            "quick_actions": actions,
            "activities": activity,
            "notifications": notifications,
            "q": q,
            "search_results": search_results,
            "system_settings": settings_obj,
            "course_performance": course_performance,
            "recent_students_table": Student.objects.select_related("user").order_by("-created_at")[:8],
            "recent_payments_table": recent_payments,
        },
    )


@role_required("ADMISSION", "ADMISSION_FINANCE")
def admission_applications(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    action = (request.GET.get("action") or "").strip()
    app_id = request.GET.get("application")

    if action in {"approve", "reject"} and app_id:
        application = get_object_or_404(AdmissionApplication, pk=app_id)
        if action == "approve":
            if not application.linked_student:
                admission_no = _next_tvet_admission_number()
                full_name = (application.full_name or "").strip()
                parts = full_name.split(maxsplit=1)
                first_name = parts[0] if parts else "Applicant"
                last_name = parts[1] if len(parts) > 1 else "Student"
                username_base = (application.email.split("@")[0] if application.email else first_name).lower()
                username = username_base
                index = 1
                while User.objects.filter(username=username).exists():
                    index += 1
                    username = f"{username_base}{index}"
                raw_password = f"Std@{get_random_string(8)}"
                with transaction.atomic():
                    user = User.objects.create(
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        email=(application.email or f"{username}@noemail.local").lower(),
                        user_type=UserType.STUDENT,
                        is_active=True,
                        password=make_password(raw_password),
                    )
                    student = Student.objects.create(
                        user=user,
                        admission_number=admission_no,
                        id_number=application.id_number,
                        phone=application.phone,
                        status="active",
                    )
                    if application.requested_program and application.requested_intake:
                        Enrollment.objects.get_or_create(
                            student=student,
                            program=application.requested_program,
                            intake=application.requested_intake,
                            defaults={"campus": application.requested_program.campus},
                        )
                    application.linked_student = student
                messages.success(
                    request,
                    f"Application approved and student created. Username: {username}, Temp password: {raw_password}",
                )
            application.status = ApplicationStatus.APPROVED
        else:
            application.status = ApplicationStatus.REJECTED
            messages.info(request, "Application rejected.")
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "reviewed_by", "reviewed_at", "linked_student"])
        return redirect("admission_applications")

    if request.method == "POST":
        form = AdmissionApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Application captured successfully.")
            return redirect("admission_applications")
    else:
        form = AdmissionApplicationForm()

    applications = AdmissionApplication.objects.select_related(
        "requested_program", "requested_intake", "reviewed_by", "linked_student"
    )
    if q:
        applications = applications.filter(
            Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(id_number__icontains=q)
        )
    if status_filter:
        applications = applications.filter(status=status_filter)
    page_obj = Paginator(applications.order_by("-applied_at"), 20).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/admission_applications.html",
        {
            "form": form,
            "page_obj": page_obj,
            "q": q,
            "status_filter": status_filter,
            "status_choices": ApplicationStatus.choices,
        },
    )


@role_required("ADMISSION_FINANCE")
def admission_finance_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    enrollments = ShortCourseEnrollment.objects.select_related("student__user", "short_course")
    payments = ShortCoursePayment.objects.select_related("enrollment__student__user", "enrollment__short_course")
    if q:
        enrollments = enrollments.filter(
            Q(student__admission_number__icontains=q)
            | Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
            | Q(short_course__name__icontains=q)
        )
        payments = payments.filter(
            Q(enrollment__student__admission_number__icontains=q)
            | Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
            | Q(mpesa_reference__icontains=q)
            | Q(reference__icontains=q)
        )
    today = timezone.localdate()
    collections_today = payments.filter(paid_on=today).aggregate(s=Sum("amount"))["s"] or 0
    outstanding_total = (
        ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).aggregate(s=Sum("balance"))["s"]
        or 0
    )
    stats = [
        {"title": "Students Registered Today", "value": Student.objects.filter(created_at__date=today).count(), "subtitle": "Newly created student records"},
        {
            "title": "Active Enrollments",
            "value": enrollments.filter(status=ShortCourseEnrollmentStatus.ACTIVE).count(),
            "subtitle": "Learners in active study",
        },
        {"title": "Daily Collections", "value": collections_today, "subtitle": "Payments posted today"},
        {"title": "Outstanding Balance", "value": outstanding_total, "subtitle": "Open student balances"},
    ]
    recent_enrollments = enrollments.order_by("-enrolled_on", "-id")[:8]
    recent_payments = payments.order_by("-recorded_at")[:8]
    outstanding_rows = (
        ShortCourseEnrollment.objects.select_related("student__user", "short_course")
        .exclude(payment_status=ShortCoursePaymentStatus.PAID)
        .order_by("-balance")[:10]
    )
    activity = []
    for e in recent_enrollments:
        activity.append(
            {
                "title": f"{e.student.user.get_full_name() or e.student.admission_number} enrolled",
                "meta": f"{e.short_course.name} / {e.get_status_display()}",
                "status": "enrolled",
                "when": timezone.make_aware(datetime.combine(e.enrolled_on, time.min)),
            }
        )
    for p in recent_payments:
        activity.append(
            {
                "title": f"Payment received {_money_whole(p.amount)}",
                "meta": f"{p.enrollment.student.admission_number} / {p.enrollment.short_course.name}",
                "status": p.method,
                "when": p.recorded_at,
            }
        )
    activity = sorted(activity, key=lambda x: x.get("when") or timezone.now(), reverse=True)[:12]
    return render(
        request,
        "dashboard/admission_finance_dashboard.html",
        {
            "page_title": "Admission & Finance Dashboard",
            "q": q,
            "stats": stats,
            "activities": activity,
            "recent_enrollments": recent_enrollments,
            "recent_payments": recent_payments,
            "outstanding_rows": outstanding_rows,
            "quick_actions": [
                {"label": "Register Student", "url": "/admin/students/"},
                {"label": "Manage Enrollments", "url": "/admin/students/#short-enrollment"},
                {"label": "Record Payment", "url": "/admin/finance/"},
                {"label": "Export Reports", "url": "/admin/reports/"},
            ],
        },
    )


@role_required("ADMISSION")
def admission_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    enrollments = Enrollment.objects.select_related("student__user", "program", "intake").order_by("-enrolled_on")
    if q:
        enrollments = enrollments.filter(
            Q(student__admission_number__icontains=q)
            | Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
            | Q(program__name__icontains=q)
        )
    today = timezone.localdate()
    admitted_today = enrollments.filter(enrolled_on=today).count()
    admitted_total = enrollments.count()
    pending_docs = Student.objects.filter(documents__isnull=True).count()
    by_program = (
        enrollments.values("program__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )
    stats = [
        {"title": "Admitted Today", "value": admitted_today, "subtitle": "New enrollments"},
        {"title": "Total Enrollments", "value": admitted_total, "subtitle": "All admitted students"},
        {"title": "Missing Documents", "value": pending_docs, "subtitle": "Need verification"},
        {"title": "Active Intakes", "value": Intake.objects.count(), "subtitle": "Configured cohorts"},
    ]
    activity = [
        {
            "title": f"{e.student.user.get_full_name() or e.student.admission_number} admitted",
            "meta": f"{e.program.name} / {e.intake.label}",
            "status": e.status,
            "when": timezone.make_aware(datetime.combine(e.enrolled_on, time.min)),
        }
        for e in enrollments[:10]
    ]
    notifications = []
    if pending_docs:
        notifications.append(f"{pending_docs} students are missing mandatory documents.")
    return render(
        request,
        "dashboard/admission_dashboard.html",
        {
            "page_title": "Admissions",
            "stats": stats,
            "activities": activity,
            "notifications": notifications,
            "q": q,
            "program_rows": by_program,
            "quick_actions": [
                {"label": "Capture Application", "url": "/admin/admissions/"},
                {"label": "Register Student", "url": "/admin/students/"},
                {"label": "Verify Documents", "url": "/admin/students/#documents"},
                {"label": "Admission Reports", "url": "/admin/reports/"},
            ],
        },
    )


@role_required("TRAINER")
def trainer_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    attempts = ShortCourseAssessment.objects.select_related(
        "enrollment__student__user",
        "enrollment__short_course",
    ).filter(Q(instructor=request.user) | Q(enrollment__short_course__instructor=request.user))
    if q:
        attempts = attempts.filter(
            Q(enrollment__student__admission_number__icontains=q)
            | Q(enrollment__short_course__course_code__icontains=q)
            | Q(enrollment__short_course__name__icontains=q)
        )
    recent_attempts = attempts.order_by("-assessed_at")[:10]
    today = timezone.localdate()
    assigned_units = ShortCourse.objects.filter(instructor=request.user, is_active=True).distinct()
    timetable = ShortCourseSession.objects.filter(instructor=request.user).select_related("short_course").order_by("session_date", "session_time")[:10]
    today_sessions = ShortCourseSession.objects.filter(
        instructor=request.user,
        session_date=today,
        status=ShortCourseSession.Status.SCHEDULED,
    ).select_related("short_course").order_by("session_time")
    upcoming_sessions = ShortCourseSession.objects.filter(
        instructor=request.user,
        session_date__gt=today,
        status=ShortCourseSession.Status.SCHEDULED,
    ).select_related("short_course").order_by("session_date", "session_time")[:10]
    weak_students = (
        attempts.filter(outcome=ShortCourseAssessment.Outcome.FAIL)
        .values("enrollment__student__admission_number", "enrollment__student__user__first_name", "enrollment__student__user__last_name")
        .annotate(nyc_count=Count("id"))
        .order_by("-nyc_count")[:8]
    )

    stats = [
        {
            "title": "Practical assessments",
            "value": attempts.count(),
            "subtitle": "All recorded skill assessments",
        },
        {
            "title": "Today",
            "value": ShortCourseSession.objects.filter(instructor=request.user, session_date=today).count(),
            "subtitle": "Sessions scheduled today",
        },
        {
            "title": "Learners needing support",
            "value": attempts.filter(outcome=ShortCourseAssessment.Outcome.FAIL).count(),
            "subtitle": "Below pass threshold",
        },
        {
            "title": "Assigned courses",
            "value": assigned_units.count(),
            "subtitle": "Courses available to teach",
        },
    ]
    actions = [
        {"label": "Mark Attendance", "url": "/admin/courses/#attendance"},
        {"label": "Add Session", "url": "/admin/courses/"},
    ]
    activity = [
        {
            "title": f"{a.enrollment.student.admission_number} - {a.enrollment.short_course.name}",
            "meta": f"Rating {(a.skill_rating if a.skill_rating is not None else '-')} / {a.assessed_at:%Y-%m-%d %H:%M}",
            "status": a.outcome or "pending",
        }
        for a in recent_attempts
    ]
    notifications = []
    if attempts.filter(outcome=ShortCourseAssessment.Outcome.FAIL).exists():
        notifications.append("Some learners are below pass threshold and may need retakes.")
    return render(
        request,
        "dashboard/trainer_dashboard.html",
        {
            "page_title": "Lecturer Dashboard",
            "stats": stats,
            "quick_actions": actions,
            "activities": activity,
            "notifications": notifications,
            "q": q,
            "assigned_units": assigned_units[:20],
            "timetable": timetable,
            "today_sessions": today_sessions,
            "upcoming_sessions": upcoming_sessions,
            "weak_students": weak_students,
        },
    )


@role_required("FINANCE")
def finance_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    payments = ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course")
    if q:
        payments = payments.filter(
            Q(mpesa_reference__icontains=q)
            | Q(reference__icontains=q)
            | Q(enrollment__student__admission_number__icontains=q)
            | Q(enrollment__short_course__name__icontains=q)
        )
    recent_payments = payments.order_by("-recorded_at")[:10]
    paid_today = ShortCoursePayment.objects.filter(paid_on=timezone.localdate())
    outstanding_amount = (
        ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).aggregate(s=Sum("balance"))["s"] or 0
    )
    overdue_invoices = (
        ShortCourseEnrollment.objects.select_related("student__user", "short_course")
        .exclude(payment_status=ShortCoursePaymentStatus.PAID)
        .order_by("-balance")[:10]
    )
    failed_transactions = MpesaCallbackLog.objects.filter(result_code__gt=0).order_by("-created_at")[:8]

    students_with_balances = (
        ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).values("student_id").distinct().count()
    )
    short_course_revenue = ShortCoursePayment.objects.aggregate(s=Sum("amount"))["s"] or 0
    short_course_outstanding = (
        ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).aggregate(s=Sum("balance"))["s"]
        or 0
    )
    stats = [
        {
            "title": "Total Revenue",
            "value": short_course_revenue,
            "subtitle": "ICT short courses",
        },
        {"title": "Outstanding Course Fees", "value": outstanding_amount, "subtitle": "Unpaid balances"},
        {"title": "Students With Balances", "value": students_with_balances, "subtitle": "Need follow-up"},
        {"title": "Payments Today", "value": paid_today.count(), "subtitle": "Transactions"},
    ]
    actions = [
        {"label": "Record Payment", "url": "/admin/finance/"},
        {"label": "View Invoices", "url": "/admin/finance/#invoices"},
        {"label": "View Reports", "url": "/admin/reports/"},
    ]
    activity = []
    for p in recent_payments:
        learner = p.enrollment.student.admission_number if p.enrollment_id else "N/A"
        activity.append(
            {
                "title": f"{learner} paid {_money_whole(p.amount)}",
                "meta": f"{p.method} / {p.mpesa_reference or p.reference}",
                "status": "received",
            }
        )
    notifications = []
    if outstanding_amount:
        notifications.append("Outstanding balances exist; send fee reminders.")
    if short_course_outstanding:
        notifications.append("Some short-course enrollments have pending balances.")
    if failed_transactions:
        notifications.append("Some M-Pesa callbacks failed and require review.")
    return render(
        request,
        "dashboard/finance_dashboard.html",
        {
            "page_title": "Finance",
            "stats": stats,
            "quick_actions": actions,
            "activities": activity,
            "notifications": notifications,
            "q": q,
            "overdue_invoices": overdue_invoices,
            "failed_transactions": failed_transactions,
        },
    )


@student_required
def student_dashboard(request):
    q = (request.GET.get("q") or "").strip()
    ctx = {
        "page_title": "Student Dashboard",
        "student_record": None,
        "stats": [],
        "quick_actions": [
            {"label": "My courses", "url": "/student-dashboard/#short-courses"},
            {"label": "Attendance", "url": "/student-dashboard/#attendance"},
            {"label": "Payments", "url": "/student-dashboard/#finance"},
            {"label": "Certificates", "url": "/student-dashboard/#short-courses"},
        ],
        "activities": [],
        "notifications": [],
        "short_course_enrollments": [],
        "short_course_certificates": [],
        "short_course_sessions": [],
        "short_course_attendance": [],
        "short_course_payments": [],
        "next_class": None,
        "q": q,
    }
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        student = None
    if student:
        ctx["student_record"] = student
        short_course_enrollments = (
            ShortCourseEnrollment.objects.select_related("short_course")
            .filter(student=student)
            .order_by("-enrolled_on")
        )
        enrollment_ids = list(short_course_enrollments.values_list("id", flat=True))
        short_course_certificates = (
            ShortCourseCertificate.objects.select_related("enrollment__short_course")
            .filter(enrollment__student=student)
            .order_by("-issued_at")
        )
        short_course_payments = (
            ShortCoursePayment.objects.select_related("enrollment__short_course")
            .filter(enrollment__student=student)
            .order_by("-recorded_at")
        )
        short_course_sessions = (
            ShortCourseSession.objects.select_related("short_course", "instructor")
            .filter(short_course__enrollments__student=student)
            .distinct()
            .order_by("session_date", "session_time")[:10]
        )
        today = timezone.localdate()
        upcoming_only = [
            s for s in short_course_sessions if s.session_date and s.session_date >= today and s.status == ShortCourseSession.Status.SCHEDULED
        ]
        attendance_qs = (
            ShortCourseAttendance.objects.select_related("session__short_course", "enrollment")
            .filter(enrollment_id__in=enrollment_ids)
        )
        attendance_map = {}
        for row in attendance_qs:
            course_id = row.enrollment.short_course_id
            bucket = attendance_map.setdefault(
                course_id,
                {"course": row.enrollment.short_course, "present": 0, "total": 0},
            )
            bucket["total"] += 1
            if row.status == ShortCourseAttendance.Status.PRESENT:
                bucket["present"] += 1
        attendance_rows = []
        for item in attendance_map.values():
            total = item["total"] or 1
            attendance_rows.append(
                {
                    "course": item["course"],
                    "percentage": round((item["present"] / total) * 100, 2),
                    "present": item["present"],
                    "total": item["total"],
                }
            )
        outstanding = short_course_enrollments.exclude(payment_status=ShortCoursePaymentStatus.PAID).aggregate(s=Sum("balance"))["s"] or 0
        avg_progress = short_course_enrollments.aggregate(s=Sum("progress_percent"))["s"] or 0
        avg_progress = round(avg_progress / short_course_enrollments.count(), 2) if short_course_enrollments.count() else 0

        ctx["stats"] = [
            {"title": "Enrolled Courses", "value": short_course_enrollments.count(), "subtitle": "Active + completed"},
            {"title": "Average Progress", "value": f"{avg_progress}%", "subtitle": "Across your courses"},
            {"title": "Certificates", "value": short_course_certificates.count(), "subtitle": "Issued"},
            {"title": "Outstanding Balance", "value": outstanding, "subtitle": "Pending course fees"},
        ]
        ctx["short_course_enrollments"] = short_course_enrollments
        ctx["short_course_certificates"] = short_course_certificates
        ctx["short_course_sessions"] = upcoming_only
        ctx["next_class"] = upcoming_only[0] if upcoming_only else None
        ctx["short_course_attendance"] = attendance_rows
        ctx["short_course_payments"] = short_course_payments[:10]
        ctx["activities"] = [
            {
                "title": f"Enrolled: {e.short_course.name}",
                "meta": f"{e.enrolled_on} / {e.status}",
                "status": e.payment_status,
            }
            for e in short_course_enrollments[:5]
        ] + [
            {
                "title": f"Payment {_money_whole(p.amount)}",
                "meta": f"{p.paid_on} / {p.mpesa_reference or p.reference or 'manual'}",
                "status": "received",
            }
            for p in short_course_payments[:5]
        ]
        if outstanding > 0:
            ctx["notifications"].append("You have unpaid course balance. Please pay via M-Pesa or office.")
        low_attendance = [r for r in attendance_rows if r["percentage"] < 75]
        if low_attendance:
            ctx["notifications"].append(f"Low attendance on {len(low_attendance)} course(s).")
    return render(request, "dashboard/student_dashboard.html", ctx)


@student_required
def student_results_slip_download(request):
    student = get_object_or_404(Student, user=request.user)
    enrollment = student.enrollments.filter(status=EnrollmentStatus.ACTIVE).select_related("program").first()
    results = Result.objects.select_related("unit").filter(student=student)
    if enrollment:
        results = results.filter(unit__program=enrollment.program)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="results-slip-{student.admission_number}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Admission Number", student.admission_number])
    writer.writerow(["Student Name", request.user.get_full_name() or request.user.username])
    writer.writerow(["Program", enrollment.program.name if enrollment else ""])
    writer.writerow([])
    writer.writerow(["Course Code", "Course Name", "Score", "Final Status", "Updated At"])
    for row in results.order_by("unit__title"):
        writer.writerow([row.unit.code, row.unit.title, row.final_score, row.final_status, row.updated_at.strftime("%Y-%m-%d")])
    return response


@student_required
def student_fee_statement_download(request):
    student = get_object_or_404(Student, user=request.user)
    invoices = Invoice.objects.filter(student=student).select_related("enrollment__program")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="fee-statement-{student.admission_number}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Admission Number", student.admission_number])
    writer.writerow(["Student Name", request.user.get_full_name() or request.user.username])
    writer.writerow([])
    writer.writerow(["Invoice ID", "Program", "Total", "Balance", "Status", "Created"])
    for inv in invoices.order_by("-created_at"):
        writer.writerow(
            [
                inv.pk,
                getattr(inv.enrollment.program, "name", ""),
                _money_whole(inv.total_amount),
                _money_whole(inv.balance),
                inv.get_status_display(),
                inv.created_at.strftime("%Y-%m-%d"),
            ]
        )
    writer.writerow([])
    writer.writerow(["Receipt", "Date", "Amount", "Method", "Reference"])
    payments = Payment.objects.filter(invoice__student=student).select_related("invoice").order_by("-recorded_at")
    for p in payments:
        writer.writerow(
            [p.receipt_number, p.paid_on, _money_whole(p.amount), p.get_method_display(), p.transaction_code or p.reference]
        )
    return response


@student_required
def short_course_certificate_download(request, certificate_id: int):
    student = get_object_or_404(Student, user=request.user)
    certificate = get_object_or_404(
        ShortCourseCertificate.objects.select_related("enrollment__short_course", "enrollment__student__user"),
        pk=certificate_id,
        enrollment__student=student,
    )
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        response = HttpResponse(content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="short-course-certificate-{certificate.certificate_number}.txt"'
        response.write("COLLEGE MANAGEMENT SYSTEM - COURSE CERTIFICATE\n")
        response.write(f"Certificate Number: {certificate.certificate_number}\n")
        response.write(f"Student: {student.user.get_full_name() or student.admission_number}\n")
        response.write(f"Course: {certificate.enrollment.short_course.name}\n")
        response.write(f"Completion Date: {certificate.issued_at:%Y-%m-%d}\n")
        return response

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 80
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2, y, "Certificate of Completion")
    y -= 36
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2, y, "College Management System")
    y -= 48
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2, y, "This certifies that")
    y -= 28
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, y, student.user.get_full_name() or student.admission_number)
    y -= 36
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2, y, "has successfully completed the course")
    y -= 24
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2, y, certificate.enrollment.short_course.name)
    y -= 40
    p.setFont("Helvetica", 11)
    p.drawCentredString(width / 2, y, f"Certificate No: {certificate.certificate_number}")
    y -= 18
    p.drawCentredString(width / 2, y, f"Completion Date: {certificate.issued_at:%Y-%m-%d}")
    p.showPage()
    p.save()
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="short-course-certificate-{certificate.certificate_number}.pdf"'
    return response


@role_required("PARENT")
def parent_dashboard(request):
    profile = getattr(request.user, "parent_profile", None)
    students = profile.students.select_related("user").prefetch_related("results__unit")[:50] if profile else []
    cards = [
        {"title": "Linked Students", "value": len(students), "subtitle": "Children/Dependants"},
    ]
    child_rows = []
    for s in students:
        competent = s.results.filter(final_status=CompetencyGrade.COMPETENT).count()
        total = s.results.count()
        child_rows.append(
            {
                "student": s,
                "competent": competent,
                "total": total,
                "progress": round((competent / total) * 100, 2) if total else 0,
            }
        )
    return render(request, "dashboard/parent_dashboard.html", {"stats": cards, "children": child_rows, "page_title": "Parent"})


@student_required
def course_registration(request):
    student = get_object_or_404(Student.objects.select_related("user"), user=request.user)
    enrollment = student.enrollments.filter(status=EnrollmentStatus.ACTIVE).select_related("program").first()
    if not enrollment:
        messages.error(request, "No active enrollment found for course registration.")
        return redirect("student_dashboard")

    if request.method == "POST":
        form = CourseRegistrationForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.enrollment = enrollment
            try:
                obj.full_clean()
                obj.save()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Course registration updated.")
                return redirect("course_registration")
    else:
        form = CourseRegistrationForm(initial={"semester": Semester.SEM1, "status": RegistrationStatus.REGISTERED})

    form.fields["unit"].queryset = Unit.objects.filter(program=enrollment.program).order_by("title")
    regs = CourseRegistration.objects.filter(enrollment=enrollment).select_related("unit").order_by("-updated_at")
    return render(
        request,
        "dashboard/course_registration.html",
        {
            "enrollment": enrollment,
            "form": form,
            "registrations_page": Paginator(regs, 20).get_page(request.GET.get("page")),
        },
    )


def _sync_role_profile_links(user: User, admission_number: str = "", program=None, intake=None):
    if user.user_type == UserType.TRAINER:
        TrainerProfile.objects.get_or_create(user=user)
    if user.user_type == UserType.FINANCE:
        FinanceProfile.objects.get_or_create(user=user)
    if user.user_type == UserType.STUDENT:
        admission = (admission_number or "").strip() or f"ADM-{user.pk:05d}"
        student, _ = Student.objects.get_or_create(
            user=user,
            defaults={"admission_number": admission},
        )
        if not student.admission_number:
            student.admission_number = admission
            student.save(update_fields=["admission_number"])
        if program and intake:
            Enrollment.objects.get_or_create(
                student=student,
                program=program,
                intake=intake,
                defaults={"campus": program.campus},
            )


@super_admin_required
def user_management(request):
    q = (request.GET.get("q") or "").strip()
    role = (request.GET.get("role") or "").strip()
    users = User.objects.all()
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    if role:
        users = users.filter(user_type=role)
    generated = request.session.pop("generated_credentials", None)
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            full_name = (form.cleaned_data.get("full_name") or "").strip()
            parts = full_name.split(maxsplit=1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""
            auto_username = form.cleaned_data.get("auto_generate_username")
            auto_password = form.cleaned_data.get("auto_generate_password")
            username = (form.cleaned_data.get("username") or "").strip()
            if auto_username or not username:
                base = (
                    (form.cleaned_data.get("email") or "").split("@")[0]
                    or f"{first_name}.{last_name}".strip(".")
                    or "user"
                ).lower().replace(" ", ".")
                candidate = base
                i = 1
                while User.objects.filter(username=candidate).exists():
                    i += 1
                    candidate = f"{base}{i}"
                username = candidate
            raw_password = form.cleaned_data.get("password")
            if auto_password or not raw_password:
                raw_password = f"Pass@{get_random_string(8)}"
            u = form.save(commit=False)
            u.username = username
            u.first_name = first_name
            u.last_name = last_name
            u.user_type = form.cleaned_data["role"]
            u.password = make_password(raw_password)
            u.apply_role_permissions()
            u.save()
            _sync_role_profile_links(
                u,
                admission_number=form.cleaned_data.get("admission_number") or "",
                program=form.cleaned_data.get("program"),
                intake=form.cleaned_data.get("intake"),
            )
            AuditLog.objects.create(
                user=request.user,
                action="create_user",
                module="accounts",
                path=request.path,
                method=request.method,
                status_code=200,
                metadata={"target_user_id": u.id, "role": u.user_type},
            )
            request.session["generated_credentials"] = {
                "username": username,
                "password": raw_password,
                "role": u.get_user_type_display(),
            }
            messages.success(request, "User created successfully.")
            return redirect("user_management")
    else:
        form = UserCreateForm()
    page_obj = Paginator(users.order_by("-date_joined"), 20).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/user_management.html",
        {"page_obj": page_obj, "form": form, "q": q, "role": role, "generated_credentials": generated},
    )


@super_admin_required
def user_update(request, user_id: int):
    user = get_object_or_404(User, pk=user_id)
    form = UserUpdateForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        full_name = (form.cleaned_data.get("full_name") or "").strip()
        parts = full_name.split(maxsplit=1)
        user.first_name = parts[0] if parts else ""
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.user_type = form.cleaned_data["role"]
        new_password = form.cleaned_data.get("password")
        if new_password:
            user.password = make_password(new_password)
        user.apply_role_permissions()
        user.save()
        _sync_role_profile_links(user)
        AuditLog.objects.create(
            user=request.user,
            action="update_user",
            module="accounts",
            path=request.path,
            method=request.method,
            status_code=200,
            metadata={"target_user_id": user.id, "role": user.user_type},
        )
        messages.success(request, "User updated successfully.")
        return redirect("user_management")
    return render(request, "adminpanel/user_update.html", {"form": form, "target_user": user})


@super_admin_required
def user_toggle_active(request, user_id: int):
    user = get_object_or_404(User, pk=user_id)
    if user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        AuditLog.objects.create(
            user=request.user,
            action="toggle_user_active",
            module="accounts",
            path=request.path,
            method=request.method,
            status_code=200,
            metadata={"target_user_id": user.id, "is_active": user.is_active},
        )
        messages.success(request, "User status updated.")
    return redirect("user_management")


@super_admin_required
def user_reset_password(request, user_id: int):
    user = get_object_or_404(User, pk=user_id)
    temp_password = f"Pass@{get_random_string(8)}"
    user.password = make_password(temp_password)
    user.save(update_fields=["password"])
    AuditLog.objects.create(
        user=request.user,
        action="reset_user_password",
        module="accounts",
        path=request.path,
        method=request.method,
        status_code=200,
        metadata={"target_user_id": user.id},
    )
    messages.success(request, f"Password reset for {user.username}. Temporary password: {temp_password}")
    return redirect("user_management")


@permission_required("can_view_students")
def student_management(request):
    def _next_admission_number() -> str:
        year = timezone.localdate().year
        prefix = f"COL/{year}/"
        existing = (
            Student.objects.filter(admission_number__startswith=prefix)
            .values_list("admission_number", flat=True)
        )
        max_seq = 0
        for adm in existing:
            try:
                seq = int(str(adm).split("/")[-1])
            except Exception:
                continue
            max_seq = max(max_seq, seq)
        return f"{prefix}{max_seq + 1:03d}"

    def _admit_student_payload(data: dict, files=None):
        admission_no = (data.get("admission_number") or "").strip() or _next_admission_number()
        if Student.objects.filter(admission_number=admission_no).exists():
            raise ValueError(f"Admission number already exists: {admission_no}")
        username = admission_no
        if User.objects.filter(username=username).exists():
            raise ValueError("Generated username already exists for this admission number.")
        temp_password = f"Std@{get_random_string(8)}"
        email = (data.get("email") or "").strip().lower() or f"{username}@noemail.local"
        with transaction.atomic():
            user = User.objects.create(
                username=username,
                first_name=data["first_name"].strip(),
                last_name=data["last_name"].strip(),
                email=email,
                user_type=UserType.STUDENT,
                is_active=True,
                password=make_password(temp_password),
            )
            student = Student.objects.create(
                user=user,
                admission_number=admission_no,
                gender=data["gender"],
                id_number=data["id_number"],
                passport_number=data.get("passport_number", ""),
                phone=data.get("phone", ""),
                date_of_birth=data.get("date_of_birth"),
                address=data.get("address", ""),
                previous_school=data.get("previous_school", ""),
                kcse_grade=data.get("kcse_grade", ""),
                guardian_name=data.get("guardian_name", ""),
                guardian_phone=data.get("guardian_phone", ""),
                guardian_relationship=data.get("guardian_relationship", ""),
                status=data["status"],
            )
            enrollment = None
            if data.get("program") and data.get("intake"):
                enrollment = Enrollment.objects.create(
                    student=student,
                    program=data["program"],
                    intake=data["intake"],
                    campus=data["program"].campus,
                    mode_of_study=data.get("mode_of_study"),
                    status=EnrollmentStatus.ACTIVE,
                )
                for unit in data["program"].units.all():
                    UnitAssignment.objects.get_or_create(enrollment=enrollment, unit=unit)
                    Result.objects.get_or_create(student=student, unit=unit)
                    StudentUnitResult.objects.get_or_create(
                        enrollment=enrollment,
                        unit=unit,
                        defaults={"overall_grade": CompetencyGrade.NOT_YET},
                    )
            if data.get("short_course"):
                short_enrollment = ShortCourseEnrollment.objects.create(
                    student=student,
                    short_course=data["short_course"],
                    status=ShortCourseEnrollmentStatus.ACTIVE,
                )
                initial_payment = data.get("initial_payment") or 0
                if initial_payment and initial_payment > 0:
                    ShortCoursePayment.objects.create(
                        enrollment=short_enrollment,
                        amount=initial_payment,
                        method=ShortCoursePayment.Method.MPESA,
                        reference="Admission initial payment",
                    )
            if files:
                if files.get("id_document"):
                    StudentDocument.objects.create(
                        student=student,
                        document_type=StudentDocumentType.ID_COPY,
                        file=files["id_document"],
                    )
                if files.get("certificate_document"):
                    StudentDocument.objects.create(
                        student=student,
                        document_type=StudentDocumentType.OTHER_CERT,
                        file=files["certificate_document"],
                    )
            discount = data.get("discount_amount") or 0
            invoice = getattr(enrollment, "invoice", None) if enrollment else None
            if invoice and discount > 0:
                discount = min(discount, invoice.total_amount)
                invoice.total_amount = invoice.total_amount - discount
                invoice.balance = max(invoice.balance - discount, Decimal("0"))
                invoice.status = InvoiceStatus.UNPAID if invoice.balance > 0 else InvoiceStatus.PAID
                invoice.save(update_fields=["total_amount", "balance", "status", "updated_at"])
        return username, temp_password

    q = (request.GET.get("q") or "").strip()
    course_id = request.GET.get("course")
    status = request.GET.get("status")
    students = Student.objects.select_related("user").prefetch_related("enrollments__program", "enrollments__intake")
    if q:
        students = students.filter(
            Q(admission_number__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )
    if status:
        students = students.filter(status=status)
    if request.method == "POST":
        form_type = request.POST.get("form_type", "single")
        if form_type == "bulk_students":
            upload = request.FILES.get("students_csv")
            if not upload:
                messages.error(request, "Please attach a CSV file for bulk upload.")
                admission_form = StudentAdmissionForm(initial={"status": "active"})
            else:
                created = 0
                failed = 0
                try:
                    reader = csv.DictReader(TextIOWrapper(upload.file, encoding="utf-8"))
                    for row in reader:
                        try:
                            program = Program.objects.filter(code__iexact=(row.get("program_code") or "").strip()).first()
                            intake = Intake.objects.filter(label__iexact=(row.get("intake_label") or "").strip()).first()
                            if not program or not intake:
                                raise ValueError("Program or intake not found.")
                            payload = {
                                "first_name": (row.get("first_name") or "").strip(),
                                "last_name": (row.get("last_name") or "").strip(),
                                "admission_number": (row.get("admission_number") or "").strip(),
                                "gender": (row.get("gender") or "male").strip().lower(),
                                "date_of_birth": row.get("date_of_birth") or None,
                                "id_number": (row.get("id_number") or "").strip(),
                                "passport_number": (row.get("passport_number") or "").strip(),
                                "phone": (row.get("phone") or "").strip(),
                                "email": (row.get("email") or "").strip(),
                                "address": (row.get("address") or "").strip(),
                                "status": (row.get("status") or "active").strip().lower(),
                                "mode_of_study": (row.get("mode_of_study") or "full_time").strip().lower(),
                                "guardian_name": (row.get("guardian_name") or "").strip(),
                                "guardian_phone": (row.get("guardian_phone") or "").strip(),
                                "guardian_relationship": (row.get("guardian_relationship") or "").strip(),
                                "previous_school": (row.get("previous_school") or "").strip(),
                                "kcse_grade": (row.get("kcse_grade") or "").strip(),
                                "program": program,
                                "intake": intake,
                                "discount_amount": Decimal(str(row.get("discount_amount") or "0")),
                                "short_course": ShortCourse.objects.filter(
                                    Q(course_code__iexact=(row.get("short_course_code") or "").strip())
                                    | Q(name__iexact=(row.get("short_course_name") or "").strip())
                                ).first(),
                                "initial_payment": Decimal(str(row.get("initial_payment") or "0")),
                            }
                            _admit_student_payload(payload)
                            created += 1
                        except Exception:
                            failed += 1
                    messages.success(request, f"Bulk upload complete. Created {created}, failed {failed}.")
                    return redirect("student_management")
                except Exception as exc:
                    messages.error(request, f"Bulk upload failed: {exc}")
                admission_form = StudentAdmissionForm(initial={"status": "active"})
        else:
            admission_form = StudentAdmissionForm(request.POST, request.FILES)
            if admission_form.is_valid():
                try:
                    username, temp_password = _admit_student_payload(admission_form.cleaned_data, request.FILES)
                except Exception as exc:
                    messages.error(request, f"Student admission failed: {exc}")
                else:
                    created_student = Student.objects.filter(admission_number=username).first()
                    messages.success(
                        request,
                        f"Student admitted successfully. Login username: {username}, temporary password: {temp_password}",
                    )
                    if created_student:
                        return redirect("student_profile", student_id=created_student.id)
                    return redirect("student_management")
    else:
        admission_form = StudentAdmissionForm(initial={"status": "active"})
    if course_id:
        students = students.filter(short_course_enrollments__short_course_id=course_id)
    students = students.distinct().order_by("-created_at")
    page_obj = Paginator(students, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/student_management.html",
        {
            "page_obj": page_obj,
            "admission_form": admission_form,
            "q": q,
            "course_id": course_id,
            "status": status,
            "courses": ShortCourse.objects.values_list("id", "name").order_by("name"),
            "program_fees": _program_fee_map(),
        },
    )


@permission_required("can_view_students")
def student_profile(request, student_id: int):
    student = get_object_or_404(
        Student.objects.select_related("user"),
        pk=student_id,
    )
    short_course_enrollments = (
        ShortCourseEnrollment.objects.select_related("short_course")
        .filter(student=student)
        .order_by("-enrolled_on")
    )
    payment_history = (
        ShortCoursePayment.objects.select_related("enrollment__short_course")
        .filter(enrollment__student=student)
        .order_by("-paid_on", "-recorded_at")
    )
    return render(
        request,
        "adminpanel/student_profile.html",
        {
            "student": student,
            "short_course_enrollments": short_course_enrollments,
            "payment_history": payment_history,
        },
    )


@permission_required("can_view_students")
def transcript_pdf(request, student_id: int):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    enrollment = student.enrollments.select_related("program", "intake").first()
    results = (
        Result.objects.filter(student=student).select_related("unit").order_by("unit__title")
        if enrollment
        else Result.objects.none()
    )
    grade_points = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    latest_attempts = (
        AssessmentAttempt.objects.filter(enrollment=enrollment)
        .select_related("assessment__unit")
        .order_by("assessment__unit_id", "assessment_id", "-attempt_number", "-recorded_at")
        if enrollment
        else []
    )
    latest_letter_by_unit = {}
    seen = set()
    for a in latest_attempts:
        key = (a.assessment.unit_id, a.assessment_id)
        if key in seen:
            continue
        seen.add(key)
        latest_letter_by_unit.setdefault(a.assessment.unit_id, []).append(a.letter_grade or "F")
    gpa = 0.0
    unit_count = 0
    for letters in latest_letter_by_unit.values():
        if not letters:
            continue
        points = sum(grade_points.get(l, 0) for l in letters) / len(letters)
        gpa += points
        unit_count += 1
    gpa = round(gpa / unit_count, 2) if unit_count else 0.0

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        lines = [
            f"Transcript - {student.admission_number}",
            f"Name: {student.user.get_full_name() or student.user.username}",
            f"Program: {enrollment.program.name if enrollment else '-'}",
            f"GPA: {gpa}",
            "",
        ] + [f"{r.unit.title}: {r.final_status}" for r in results]
        return HttpResponse("\n".join(lines), content_type="text/plain")

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "College Management System Transcript")
    y -= 24
    p.setFont("Helvetica", 10)
    p.drawString(40, y, f"Student: {student.user.get_full_name() or student.user.username}")
    y -= 14
    p.drawString(40, y, f"Admission No: {student.admission_number}")
    y -= 14
    p.drawString(40, y, f"Program: {enrollment.program.name if enrollment else '-'}")
    y -= 14
    p.drawString(40, y, f"GPA (MVP): {gpa}")
    y -= 20
    p.setFont("Helvetica-Bold", 10)
    p.drawString(40, y, "Course")
    p.drawString(360, y, "Final Status")
    y -= 12
    p.line(40, y, width - 40, y)
    y -= 14
    p.setFont("Helvetica", 10)
    for r in results:
        if y < 60:
            p.showPage()
            y = height - 60
        p.drawString(40, y, r.unit.title[:55])
        p.drawString(360, y, r.final_status or "-")
        y -= 14
    p.showPage()
    p.save()
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="transcript-{student.admission_number}.pdf"'
    return response


@role_required("TRAINER")
def cbet_management(request):
    short_course_form = ShortCourseForm(prefix="short_course")
    short_enrollment_form = ShortCourseEnrollmentForm(prefix="short_enrollment")
    short_session_form = ShortCourseSessionForm(prefix="short_session")
    short_attendance_form = ShortCourseAttendanceForm(prefix="short_attendance")
    short_assessment_form = ShortCourseAssessmentForm(prefix="short_assessment")
    short_payment_form = ShortCoursePaymentForm(prefix="short_payment")
    short_certificate_form = ShortCourseCertificateForm(prefix="short_certificate")
    edit_id = request.GET.get("edit_course")
    if edit_id:
        course_obj = get_object_or_404(ShortCourse, pk=edit_id)
        short_course_form = ShortCourseForm(instance=course_obj, prefix="short_course")
    edit_session_id = request.GET.get("edit_session")
    if edit_session_id:
        session_obj = get_object_or_404(ShortCourseSession, pk=edit_session_id)
        short_session_form = ShortCourseSessionForm(instance=session_obj, prefix="short_session")

    action = request.GET.get("action")
    target = request.GET.get("course")
    if action == "toggle_course" and target:
        course = get_object_or_404(ShortCourse, pk=target)
        course.is_active = not course.is_active
        course.save(update_fields=["is_active"])
        messages.success(request, "Course status updated.")
        return redirect("cbet_management")
    if action == "delete_course" and target:
        course = get_object_or_404(ShortCourse, pk=target)
        course.delete()
        messages.success(request, "Course deleted.")
        return redirect("cbet_management")
    session_action = request.GET.get("session_action")
    session_target = request.GET.get("session")
    if session_action and session_target:
        session = get_object_or_404(ShortCourseSession, pk=session_target)
        if session_action == "delete":
            session.delete()
            messages.success(request, "Session deleted.")
            return redirect("cbet_management")
        if session_action == "complete":
            session.status = ShortCourseSession.Status.COMPLETED
            session.save(update_fields=["status"])
            messages.success(request, "Session marked as completed.")
            return redirect("cbet_management")

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "short_course":
            instance = None
            course_id = request.POST.get("course_id")
            if course_id:
                instance = get_object_or_404(ShortCourse, pk=course_id)
            short_course_form = ShortCourseForm(request.POST, instance=instance, prefix="short_course")
            if short_course_form.is_valid():
                short_course_form.save()
                messages.success(request, "Course saved.")
                return redirect("cbet_management")
        elif form_type == "short_enrollment":
            short_enrollment_form = ShortCourseEnrollmentForm(request.POST, prefix="short_enrollment")
            if short_enrollment_form.is_valid():
                short_enrollment_form.save()
                messages.success(request, "Enrollment recorded.")
                return redirect("cbet_management")
        elif form_type == "short_session":
            session_id = request.POST.get("session_id")
            instance = get_object_or_404(ShortCourseSession, pk=session_id) if session_id else None
            short_session_form = ShortCourseSessionForm(request.POST, instance=instance, prefix="short_session")
            if short_session_form.is_valid():
                short_session_form.save()
                messages.success(request, "Session saved.")
                return redirect("cbet_management")
        elif form_type == "short_attendance":
            short_attendance_form = ShortCourseAttendanceForm(request.POST, prefix="short_attendance")
            if short_attendance_form.is_valid():
                short_attendance_form.save()
                messages.success(request, "Attendance marked.")
                return redirect("cbet_management")
        elif form_type == "short_assessment":
            short_assessment_form = ShortCourseAssessmentForm(request.POST, prefix="short_assessment")
            if short_assessment_form.is_valid():
                short_assessment_form.save()
                messages.success(request, "Practical assessment recorded.")
                return redirect("cbet_management")
        elif form_type == "short_payment":
            short_payment_form = ShortCoursePaymentForm(request.POST, prefix="short_payment")
            if short_payment_form.is_valid():
                short_payment_form.save()
                messages.success(request, "Course payment recorded.")
                return redirect("cbet_management")
        elif form_type == "short_certificate":
            short_certificate_form = ShortCourseCertificateForm(request.POST, prefix="short_certificate")
            if short_certificate_form.is_valid():
                cert = short_certificate_form.save(commit=False)
                if not cert.certificate_number:
                    cert.certificate_number = f"SC-{timezone.now():%Y%m%d}-{get_random_string(6).upper()}"
                cert.save()
                enrollment = cert.enrollment
                if enrollment.status != ShortCourseEnrollmentStatus.COMPLETED:
                    enrollment.status = ShortCourseEnrollmentStatus.COMPLETED
                    enrollment.completed_on = timezone.localdate()
                    enrollment.save(update_fields=["status", "completed_on"])
                messages.success(request, "Certificate generated.")
                return redirect("cbet_management")
    short_courses = ShortCourse.objects.select_related("instructor").prefetch_related("enrollments__student").order_by("name")
    short_enrollments = ShortCourseEnrollment.objects.select_related("student__user", "short_course").order_by("-enrolled_on")
    short_sessions = ShortCourseSession.objects.select_related("short_course", "instructor").order_by("-session_date", "-session_time")
    short_attendance = ShortCourseAttendance.objects.select_related("session__short_course", "enrollment__student").order_by("-marked_at")
    short_assessments = ShortCourseAssessment.objects.select_related("enrollment__student", "enrollment__short_course", "instructor").order_by("-assessed_at")
    short_payments = ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course").order_by("-recorded_at")
    short_certificates = ShortCourseCertificate.objects.select_related("enrollment__student", "enrollment__short_course").order_by("-issued_at")
    if request.user.user_type == UserType.TRAINER:
        short_courses = short_courses.filter(instructor=request.user)
        short_enrollments = short_enrollments.filter(short_course__instructor=request.user)
        short_sessions = short_sessions.filter(instructor=request.user)
        short_attendance = short_attendance.filter(session__instructor=request.user)
        short_assessments = short_assessments.filter(Q(instructor=request.user) | Q(enrollment__short_course__instructor=request.user))
        short_certificates = short_certificates.filter(enrollment__short_course__instructor=request.user)
    short_course_revenue_rows = (
        ShortCourseEnrollment.objects.values("short_course__name")
        .annotate(revenue=Sum("paid_amount"), learners=Count("id"))
        .order_by("-revenue", "short_course__name")
    )
    return render(
        request,
        "adminpanel/cbet_management.html",
        {
            "short_course_form": short_course_form,
            "short_enrollment_form": short_enrollment_form,
            "short_session_form": short_session_form,
            "short_attendance_form": short_attendance_form,
            "short_assessment_form": short_assessment_form,
            "short_payment_form": short_payment_form,
            "short_certificate_form": short_certificate_form,
            "short_courses": short_courses,
            "short_enrollments": short_enrollments,
            "short_sessions": short_sessions[:100],
            "short_attendance": short_attendance[:100],
            "short_assessments": short_assessments[:100],
            "short_payments": short_payments[:100],
            "short_certificates": short_certificates[:50],
            "short_course_revenue_rows": short_course_revenue_rows,
            "editing_course_id": int(edit_id) if (edit_id or "").isdigit() else None,
            "editing_session_id": int(edit_session_id) if (edit_session_id or "").isdigit() else None,
        },
    )


@permission_required("can_manage_assessments")
def assessment_management(request):
    entry_form = AssessmentEntryForm()
    if request.method == "POST":
        entry_form = AssessmentEntryForm(request.POST)
        if entry_form.is_valid():
            attempt = entry_form.save(commit=False)
            attempt.assessor = request.user
            try:
                attempt.full_clean()
                attempt.save()
            except ValidationError as exc:
                entry_form.add_error(None, exc)
                messages.error(request, "Assessment could not be saved. Please review the highlighted errors.")
                # Continue rendering with errors below.
            else:
                update_student_result(attempt.enrollment.student, attempt.assessment.unit)
                messages.success(request, "Assessment recorded successfully.")
                return redirect("assessment_management")

    q = (request.GET.get("q") or "").strip()
    program = request.GET.get("program")
    unit = request.GET.get("unit")
    kind = request.GET.get("kind")
    attempts = AssessmentAttempt.objects.select_related(
        "assessment__unit__program", "assessor", "enrollment__student__user"
    )
    if q:
        attempts = attempts.filter(
            Q(assessment__unit__code__icontains=q)
            | Q(assessment__unit__title__icontains=q)
            | Q(enrollment__student__admission_number__icontains=q)
            | Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
        )
    if program:
        attempts = attempts.filter(assessment__unit__program_id=program)
    if unit:
        attempts = attempts.filter(assessment__unit_id=unit)
    if kind:
        attempts = attempts.filter(assessment__kind=kind)

    # MVP unit result aggregation: average latest attempt per assessment in each unit/enrollment.
    latest_attempts = []
    seen = set()
    for a in attempts.order_by(
        "enrollment_id", "assessment__unit_id", "assessment_id", "-attempt_number", "-recorded_at"
    ):
        key = (a.enrollment_id, a.assessment_id)
        if key in seen:
            continue
        seen.add(key)
        latest_attempts.append(a)
    aggregate_map = {}
    for a in latest_attempts:
        if a.score is None:
            continue
        key = (a.enrollment_id, a.assessment.unit_id)
        if key not in aggregate_map:
            aggregate_map[key] = {"total": 0, "count": 0, "pass_mark_total": 0}
        aggregate_map[key]["total"] += float(a.score)
        aggregate_map[key]["count"] += 1
        aggregate_map[key]["pass_mark_total"] += float(a.assessment.pass_mark)
    enrollment_map = {
        e.id: e
        for e in Enrollment.objects.select_related("student__user").filter(
            id__in=[k[0] for k in aggregate_map.keys()]
        )
    }
    unit_map = {u.id: u for u in Unit.objects.select_related("program").filter(id__in=[k[1] for k in aggregate_map.keys()])}
    aggregate_rows = []
    for key, val in aggregate_map.items():
        val["avg_score"] = round(val["total"] / val["count"], 2) if val["count"] else 0
        avg_pass_mark = (val["pass_mark_total"] / val["count"]) if val["count"] else 0
        val["status"] = "C" if val["avg_score"] >= avg_pass_mark else "NYC"
        enrollment_id, unit_id = key
        aggregate_rows.append(
            {
                "enrollment_id": enrollment_id,
                "unit_id": unit_id,
                "admission_number": (
                    enrollment_map[enrollment_id].student.admission_number if enrollment_id in enrollment_map else ""
                ),
                "student_name": (
                    enrollment_map[enrollment_id].student.user.get_full_name()
                    or enrollment_map[enrollment_id].student.user.username
                    if enrollment_id in enrollment_map
                    else ""
                ),
                "unit_code": unit_map[unit_id].code if unit_id in unit_map else "",
                "unit_title": unit_map[unit_id].title if unit_id in unit_map else "",
                "avg_score": val["avg_score"],
                "status": val["status"],
            }
        )

    page_obj = Paginator(attempts.order_by("-recorded_at"), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/assessment_management.html",
        {
            "page_obj": page_obj,
            "entry_form": entry_form,
            "q": q,
            "program": program,
            "unit": unit,
            "kind": kind,
            "programs": Program.objects.order_by("code"),
            "units": Unit.objects.select_related("program").order_by("program__code", "code"),
            "kinds": AssessmentKind.choices,
            "aggregate_rows": aggregate_rows,
            "assessments": Assessment.objects.select_related("unit").order_by("unit__program__code", "unit__code", "title"),
        },
    )


@permission_required("can_manage_results")
def results_management(request):
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status")
    action = request.GET.get("action")
    if request.method == "POST" and request.POST.get("form_type") == "bulk_results":
        upload = request.FILES.get("results_csv")
        if not upload:
            messages.error(request, "Please attach a CSV file for bulk results upload.")
            return redirect("results_management")
        created = 0
        failed = 0
        reader = csv.DictReader(TextIOWrapper(upload.file, encoding="utf-8"))
        for row in reader:
            try:
                admission = (row.get("admission_number") or "").strip()
                unit_ref = (row.get("unit_title") or row.get("unit_code") or "").strip()
                status_value = (row.get("final_status") or "").strip().upper()
                score_raw = (row.get("score") or "").strip()
                student = Student.objects.filter(admission_number__iexact=admission).first()
                if not student:
                    raise ValueError("Student not found")
                unit = Unit.objects.filter(Q(title__iexact=unit_ref) | Q(code__iexact=unit_ref)).first()
                if not unit:
                    raise ValueError("Unit not found")
                if not status_value and score_raw:
                    status_value = (
                        CompetencyGrade.COMPETENT if Decimal(score_raw) >= Decimal("50") else CompetencyGrade.NOT_YET
                    )
                if status_value not in {CompetencyGrade.COMPETENT, CompetencyGrade.NOT_YET}:
                    raise ValueError("Invalid status")
                Result.objects.update_or_create(
                    student=student,
                    unit=unit,
                    defaults={"final_status": status_value},
                )
                enrollment = student.enrollments.filter(status=EnrollmentStatus.ACTIVE, program=unit.program).first()
                if enrollment:
                    StudentUnitResult.objects.update_or_create(
                        enrollment=enrollment,
                        unit=unit,
                        defaults={"overall_grade": status_value},
                    )
                created += 1
            except Exception:
                failed += 1
        messages.success(request, f"Bulk results upload complete. Processed {created}, failed {failed}.")
        return redirect("results_management")

    if action == "request_publish":
        ApprovalTask.objects.create(
            task_type=ApprovalType.RESULTS_PUBLISH,
            requested_by=request.user,
            note="Request to publish all draft results.",
        )
        messages.success(request, "Publish request submitted for admin approval.")
        return redirect("results_management")
    if action == "publish_all" and request.user.is_superuser:
        updated = StudentUnitResult.objects.filter(
            publication_status=PublicationStatus.DRAFT
        ).update(publication_status=PublicationStatus.PUBLISHED)
        student_users = User.objects.filter(user_type=UserType.STUDENT, is_active=True).only("id")
        InAppNotification.objects.bulk_create(
            [
                InAppNotification(
                    recipient=u,
                    title="Results Published",
                    message="New results are available. Please check your dashboard.",
                    is_read=False,
                )
                for u in student_users[:500]
            ]
        )
        messages.success(request, f"Published {updated} draft result records.")
        return redirect("results_management")
    results = Result.objects.select_related("student", "unit")
    if q:
        results = results.filter(
            Q(student__admission_number__icontains=q)
            | Q(unit__code__icontains=q)
            | Q(unit__title__icontains=q)
        )
    if status:
        results = results.filter(final_status=status)
    page_obj = Paginator(results.order_by("-updated_at"), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/results_management.html",
        {"page_obj": page_obj, "q": q, "status": status},
    )


@permission_required("can_manage_finance")
def finance_management(request):
    edit_payment_id = (request.GET.get("edit_payment_id") or request.POST.get("edit_payment_id") or "").strip()
    editing_payment = None
    if edit_payment_id:
        editing_payment = get_object_or_404(
            ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course"),
            pk=edit_payment_id,
        )
        if not request.user.is_superuser:
            messages.error(request, "Only Super Admin can edit payments.")
            return redirect("finance_management")
    payment_form = ShortCoursePaymentForm(prefix="short_payment", instance=editing_payment)
    status_filter = request.GET.get("status")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if request.method == "POST":
        payment_form = ShortCoursePaymentForm(request.POST, prefix="short_payment", instance=editing_payment)
        if payment_form.is_valid():
            payment_form.save()
            if editing_payment:
                messages.success(request, "Enrollment payment updated successfully.")
            else:
                messages.success(request, "Enrollment payment recorded successfully.")
            return redirect("finance_management")

    q = (request.GET.get("q") or "").strip()
    payments = ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course")
    invoices = ShortCourseEnrollment.objects.select_related("student__user", "short_course")
    if q:
        payment_query = (
            Q(enrollment__student__admission_number__icontains=q)
            | Q(enrollment__student__user__first_name__icontains=q)
            | Q(enrollment__student__user__last_name__icontains=q)
            | Q(enrollment__student__phone__icontains=q)
            | Q(mpesa_reference__icontains=q)
            | Q(reference__icontains=q)
        )
        invoice_query = (
            Q(student__admission_number__icontains=q)
            | Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
            | Q(student__phone__icontains=q)
            | Q(short_course__name__icontains=q)
        )
        if q.isdigit():
            payment_query = payment_query | Q(enrollment_id=int(q))
            invoice_query = invoice_query | Q(id=int(q))
        payments = payments.filter(payment_query)
        invoices = invoices.filter(invoice_query)
    if status_filter == "paid":
        invoices = invoices.filter(payment_status=ShortCoursePaymentStatus.PAID)
    elif status_filter == "with_balance":
        invoices = invoices.exclude(payment_status=ShortCoursePaymentStatus.PAID)
    if date_from:
        payments = payments.filter(paid_on__gte=date_from)
    if date_to:
        payments = payments.filter(paid_on__lte=date_to)

    if request.GET.get("export") == "payments_csv":
        rows = ["enrollment_id,student,course,amount,method,date,mpesa_reference,reference"]
        for p in payments.order_by("-paid_on", "-recorded_at"):
            student_ref = p.enrollment.student.admission_number
            rows.append(
                f"{p.enrollment_id},{student_ref},{p.enrollment.short_course.name},{_money_whole(p.amount)},{p.method},{p.paid_on},{p.mpesa_reference},{p.reference}"
            )
        return HttpResponse("\n".join(rows), content_type="text/csv")

    if request.GET.get("export") == "outstanding_csv":
        rows = ["enrollment_id,student,course,total,paid,balance,status"]
        for i in invoices.exclude(payment_status=ShortCoursePaymentStatus.PAID).order_by("-enrolled_on"):
            rows.append(
                f"{i.id},{i.student.admission_number},{i.short_course.name},{_money_whole(i.short_course.fee_amount)},{_money_whole(i.paid_amount)},{_money_whole(i.balance)},{i.payment_status}"
            )
        return HttpResponse("\n".join(rows), content_type="text/csv")

    return render(
        request,
        "adminpanel/finance_management.html",
        {
            "invoices_page": Paginator(invoices.order_by("-enrolled_on"), 25).get_page(request.GET.get("inv_page")),
            "payments_page": Paginator(payments.order_by("-recorded_at"), 25).get_page(request.GET.get("page")),
            "payment_form": payment_form,
            "editing_payment": editing_payment,
            "q": q,
            "status_filter": status_filter,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@permission_required("can_manage_finance")
def payment_receipt(request, payment_id: int):
    payment = get_object_or_404(Payment.objects.select_related("invoice__student__user"), pk=payment_id)
    return render(request, "adminpanel/payment_receipt.html", {"payment": payment})


@admin_required
def attachment_management(request):
    placement_form = PlacementForm(prefix="placement")
    eval_form = SupervisorEvaluationForm(prefix="evaluation")
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "placement":
            placement_form = PlacementForm(request.POST, prefix="placement")
            if placement_form.is_valid():
                placement_form.save()
                messages.success(request, "Placement assigned.")
                return redirect("attachment_management")
        elif form_type == "evaluation":
            eval_form = SupervisorEvaluationForm(request.POST, prefix="evaluation")
            if eval_form.is_valid():
                eval_form.save()
                messages.success(request, "Evaluation recorded.")
                return redirect("attachment_management")
    placements = Placement.objects.select_related("enrollment__student").order_by("-start_date")
    return render(
        request,
        "adminpanel/attachment_management.html",
        {"placements": placements[:200], "placement_form": placement_form, "eval_form": eval_form},
    )


@admin_required
def timetable_management(request):
    session_form = ClassSessionForm(prefix="session")
    attendance_form = AttendanceRecordForm(prefix="attendance")
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "session":
            session_form = ClassSessionForm(request.POST, prefix="session")
            if session_form.is_valid():
                obj = session_form.save(commit=False)
                obj.full_clean()
                obj.save()
                messages.success(request, "Class session scheduled.")
                return redirect("timetable_management")
        elif form_type == "attendance":
            attendance_form = AttendanceRecordForm(request.POST, prefix="attendance")
            if attendance_form.is_valid():
                attendance_form.save()
                messages.success(request, "Attendance marked.")
                return redirect("timetable_management")
    sessions = ClassSession.objects.select_related("unit__program", "trainer", "room").order_by("-starts_at")
    attendance = AttendanceRecord.objects.select_related("session__unit", "student").order_by("-marked_at")
    return render(
        request,
        "adminpanel/timetable_management.html",
        {
            "session_form": session_form,
            "attendance_form": attendance_form,
            "sessions_page": Paginator(sessions, 20).get_page(request.GET.get("session_page")),
            "attendance_page": Paginator(attendance, 20).get_page(request.GET.get("attendance_page")),
        },
    )


@admin_required
def library_management(request):
    book_form = BookForm(prefix="book")
    issue_form = BookIssueForm(prefix="issue")
    return_issue_id = request.GET.get("return_issue")
    if return_issue_id:
        issue = get_object_or_404(BookIssue, pk=return_issue_id, returned_on__isnull=True)
        issue.returned_on = timezone.localdate()
        issue.save(update_fields=["returned_on"])
        issue.book.available_copies = (issue.book.available_copies or 0) + 1
        if issue.book.available_copies > issue.book.total_copies:
            issue.book.available_copies = issue.book.total_copies
        issue.book.save(update_fields=["available_copies"])
        messages.success(request, "Book returned successfully.")
        return redirect("library_management")
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "book":
            book_form = BookForm(request.POST, prefix="book")
            if book_form.is_valid():
                book_form.save()
                messages.success(request, "Book added to library.")
                return redirect("library_management")
        elif form_type == "issue":
            issue_form = BookIssueForm(request.POST, prefix="issue")
            if issue_form.is_valid():
                issue = issue_form.save(commit=False)
                if issue.book.available_copies <= 0:
                    issue_form.add_error("book", "No available copies for this book.")
                else:
                    issue.full_clean()
                    issue.save()
                    issue.book.available_copies -= 1
                    issue.book.save(update_fields=["available_copies"])
                    messages.success(request, "Book issued successfully.")
                    return redirect("library_management")
    books = Book.objects.order_by("title")
    issues = BookIssue.objects.select_related("book", "student").order_by("-issued_on")
    overdue_count = sum(1 for i in issues if i.is_overdue)
    return render(
        request,
        "adminpanel/library_management.html",
        {
            "book_form": book_form,
            "issue_form": issue_form,
            "books_page": Paginator(books, 20).get_page(request.GET.get("book_page")),
            "issues_page": Paginator(issues, 20).get_page(request.GET.get("issue_page")),
            "overdue_count": overdue_count,
        },
    )


@admin_required
def communication_management(request):
    announcement_form = AnnouncementForm(prefix="announcement")
    notification_form = InAppNotificationForm(prefix="notification")
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "announcement":
            announcement_form = AnnouncementForm(request.POST, prefix="announcement")
            if announcement_form.is_valid():
                obj = announcement_form.save(commit=False)
                obj.created_by = request.user
                obj.save()
                messages.success(request, "Announcement published.")
                return redirect("communication_management")
        elif form_type == "notification":
            notification_form = InAppNotificationForm(request.POST, prefix="notification")
            if notification_form.is_valid():
                notification_form.save()
                messages.success(request, "In-app notification created.")
                return redirect("communication_management")
    announcements = Announcement.objects.select_related("program", "intake", "created_by").order_by("-created_at")
    notifications = InAppNotification.objects.select_related("recipient").order_by("-created_at")
    return render(
        request,
        "adminpanel/communication_management.html",
        {
            "announcement_form": announcement_form,
            "notification_form": notification_form,
            "announcements_page": Paginator(announcements, 20).get_page(request.GET.get("announcement_page")),
            "notifications_page": Paginator(notifications, 20).get_page(request.GET.get("notification_page")),
        },
    )


@admin_required
def approvals_management(request):
    action = request.GET.get("action")
    task_id = request.GET.get("task")
    if action in {"approve", "reject"} and task_id:
        task = get_object_or_404(ApprovalTask, pk=task_id)
        task.status = ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
        task.reviewed_by = request.user
        task.reviewed_at = timezone.now()
        task.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        if task.status == ApprovalStatus.APPROVED and task.task_type == ApprovalType.RESULTS_PUBLISH:
            StudentUnitResult.objects.filter(publication_status=PublicationStatus.DRAFT).update(
                publication_status=PublicationStatus.PUBLISHED
            )
        messages.success(request, f"Approval task {task.status}.")
        return redirect("approvals_management")
    tasks = ApprovalTask.objects.select_related("requested_by", "reviewed_by").order_by("-created_at")
    return render(
        request,
        "adminpanel/approvals_management.html",
        {"tasks_page": Paginator(tasks, 25).get_page(request.GET.get("page"))},
    )


@admin_required
def audit_logs(request):
    q = (request.GET.get("q") or "").strip()
    logs = AuditLog.objects.select_related("user")
    if q:
        logs = logs.filter(
            Q(action__icontains=q)
            | Q(path__icontains=q)
            | Q(user__username__icontains=q)
            | Q(module__icontains=q)
        )
    return render(
        request,
        "adminpanel/audit_logs.html",
        {"logs_page": Paginator(logs.order_by("-created_at"), 50).get_page(request.GET.get("page")), "q": q},
    )


@permission_required("can_view_reports")
def reports_management(request):
    enrollment_count = ShortCourseEnrollment.objects.count()
    programs = ShortCourse.objects.filter(is_active=True).count()
    short_courses_count = ShortCourse.objects.count()
    completion_rate = 0
    if enrollment_count:
        completed = ShortCourseEnrollment.objects.filter(status=ShortCourseEnrollmentStatus.COMPLETED).count()
        completion_rate = round((completed / enrollment_count) * 100, 2)
    finance_summary = {
        "revenue": ShortCoursePayment.objects.aggregate(s=Sum("amount"))["s"] or 0,
        "outstanding": ShortCourseEnrollment.objects.exclude(payment_status=ShortCoursePaymentStatus.PAID).aggregate(s=Sum("balance"))["s"] or 0,
    }
    report_type = request.GET.get("report")
    if request.GET.get("export") == "csv":
        if report_type == "revenue":
            rows = ["date,amount,student,course,method"]
            for p in ShortCoursePayment.objects.select_related("enrollment__student", "enrollment__short_course").order_by("-paid_on", "-recorded_at")[:5000]:
                rows.append(f"{p.paid_on},{_money_whole(p.amount)},{p.enrollment.student.admission_number},{p.enrollment.short_course.name},{p.method}")
            return HttpResponse("\n".join(rows), content_type="text/csv")
        if report_type == "outstanding":
            rows = ["student,course,total,balance,status"]
            for i in ShortCourseEnrollment.objects.select_related("student", "short_course").exclude(payment_status=ShortCoursePaymentStatus.PAID):
                rows.append(
                    f"{i.student.admission_number},{i.short_course.name},{_money_whole(i.short_course.fee_amount)},{_money_whole(i.balance)},{i.payment_status}"
                )
            return HttpResponse("\n".join(rows), content_type="text/csv")
        if report_type == "fee_status":
            rows = ["student,course,total,paid,balance,status"]
            for i in ShortCourseEnrollment.objects.select_related("student", "short_course"):
                rows.append(
                    f"{i.student.admission_number},{i.short_course.name},{_money_whole(i.short_course.fee_amount)},{_money_whole(i.paid_amount)},{_money_whole(i.balance)},{i.payment_status}"
                )
            return HttpResponse("\n".join(rows), content_type="text/csv")
        rows = [
            "metric,value",
            f"enrollments,{enrollment_count}",
            f"programs,{programs}",
            f"short_courses,{short_courses_count}",
            f"completion_rate,{completion_rate}",
            f"revenue,{_money_whole(finance_summary['revenue'])}",
            f"outstanding,{_money_whole(finance_summary['outstanding'])}",
        ]
        return HttpResponse("\n".join(rows), content_type="text/csv")
    return render(
        request,
        "adminpanel/reports_management.html",
        {
            "enrollment_count": enrollment_count,
            "program_count": programs,
            "short_course_count": short_courses_count,
            "completion_rate": completion_rate,
            "finance_summary": finance_summary,
        },
    )


@admin_required
def system_settings(request):
    obj, _ = SystemSetting.objects.get_or_create(pk=1)
    if request.method == "POST":
        form = SystemSettingForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
            return redirect("system_settings")
    else:
        form = SystemSettingForm(instance=obj)
    return render(request, "adminpanel/system_settings.html", {"form": form})
