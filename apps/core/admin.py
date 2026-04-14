from django.contrib import admin

from .models import ApprovalTask, AuditLog, Campus, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "academic_year", "intake_periods", "updated_at")


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "location")


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = ("task_type", "requested_by", "status", "created_at", "reviewed_at")
    list_filter = ("task_type", "status")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "module", "action", "status_code")
    list_filter = ("module", "status_code")
    search_fields = ("action", "path", "user__username")
