from django.contrib import admin

from .models import (
    CompetencyUnit,
    CourseRegistration,
    LearningOutcome,
    Program,
    ShortCourse,
    ShortCourseAttendance,
    ShortCourseAssessment,
    ShortCourseCertificate,
    ShortCourseEnrollment,
    ShortCoursePayment,
    ShortCourseSession,
    Unit,
    UnitTrainerAssignment,
)


class LearningOutcomeInline(admin.TabularInline):
    model = LearningOutcome
    extra = 0


class CompetencyUnitInline(admin.TabularInline):
    model = CompetencyUnit
    extra = 0


class UnitTrainerAssignmentInline(admin.TabularInline):
    model = UnitTrainerAssignment
    extra = 0


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "course_type", "campus", "level", "duration_months", "is_active")
    list_filter = ("course_type", "level", "is_active")
    inlines = [UnitInline]


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "program", "kind", "credit_hours")
    list_filter = ("program", "kind")
    filter_horizontal = ("prerequisites",)
    inlines = [LearningOutcomeInline, CompetencyUnitInline, UnitTrainerAssignmentInline]


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "unit", "semester", "status", "created_at")
    list_filter = ("semester", "status", "unit__program")


@admin.register(ShortCourse)
class ShortCourseAdmin(admin.ModelAdmin):
    list_display = ("course_code", "name", "category", "level", "duration_value", "duration_unit", "fee_amount", "instructor", "is_active")
    list_filter = ("category", "duration_unit", "is_active")
    search_fields = ("course_code", "name", "instructor__username", "instructor__first_name", "instructor__last_name")


@admin.register(ShortCourseEnrollment)
class ShortCourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "short_course", "status", "payment_status", "paid_amount", "balance", "progress_percent", "enrolled_on")
    list_filter = ("status", "payment_status", "short_course")
    search_fields = ("student__admission_number", "short_course__name")


@admin.register(ShortCourseSession)
class ShortCourseSessionAdmin(admin.ModelAdmin):
    list_display = ("short_course", "session_date", "session_time", "end_time", "location", "instructor", "status")
    list_filter = ("short_course", "status")


@admin.register(ShortCourseAttendance)
class ShortCourseAttendanceAdmin(admin.ModelAdmin):
    list_display = ("session", "enrollment", "status", "marked_at")
    list_filter = ("status", "session__short_course")


@admin.register(ShortCourseCertificate)
class ShortCourseCertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_number", "enrollment", "issued_at")
    search_fields = ("certificate_number", "enrollment__student__admission_number", "enrollment__short_course__name")


@admin.register(ShortCourseAssessment)
class ShortCourseAssessmentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "skill_rating", "outcome", "instructor", "assessed_at")
    list_filter = ("outcome", "enrollment__short_course")


@admin.register(ShortCoursePayment)
class ShortCoursePaymentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "amount", "method", "mpesa_reference", "paid_on")
    list_filter = ("method", "enrollment__short_course")
