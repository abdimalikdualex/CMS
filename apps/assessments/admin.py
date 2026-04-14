from django.contrib import admin

from .models import Assessment, AssessmentAttempt, AssessmentEvidence, Result, StudentUnitResult


class AssessmentEvidenceInline(admin.TabularInline):
    model = AssessmentEvidence
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "unit", "competency", "kind", "is_required")
    list_filter = ("kind", "unit__program")


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "assessment", "attempt_number", "grade", "assessor", "recorded_at")
    list_filter = ("grade", "assessment__unit__program")
    inlines = [AssessmentEvidenceInline]


@admin.register(StudentUnitResult)
class StudentUnitResultAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "unit", "overall_grade", "publication_status", "updated_at")
    list_filter = ("publication_status", "overall_grade")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("student", "unit", "final_status", "updated_at")
    list_filter = ("final_status",)
