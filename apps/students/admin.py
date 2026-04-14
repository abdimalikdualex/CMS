from django.contrib import admin

from .models import AdmissionApplication, Enrollment, Intake, Student, StudentDocument, UnitAssignment


class StudentDocumentInline(admin.TabularInline):
    model = StudentDocument
    extra = 0


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "user", "phone", "guardian_name", "status")
    list_filter = ("status",)
    search_fields = ("admission_number", "id_number", "passport_number", "user__username")
    inlines = [StudentDocumentInline]


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    list_display = ("label", "month", "year")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "campus", "intake", "mode_of_study", "status", "certificate_eligible")
    list_filter = ("status", "program", "intake", "mode_of_study")
    search_fields = ("student__admission_number",)


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ("student", "document_type", "uploaded_at")


@admin.register(UnitAssignment)
class UnitAssignmentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "unit", "assigned_at")
    list_filter = ("unit__program",)


@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "requested_program", "requested_intake", "status", "applied_at", "reviewed_by")
    list_filter = ("status", "requested_program", "requested_intake")
    search_fields = ("full_name", "email", "phone", "id_number")
