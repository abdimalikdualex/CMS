from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import FinanceProfile, ParentProfile, TrainerProfile, TrainerQualification, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "phone_number", "first_name", "last_name", "user_type", "is_active", "is_staff")
    list_filter = ("user_type", "is_staff", "is_superuser")
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Role-based access",
            {
                "fields": (
                    "user_type",
                    "phone_number",
                    "can_view",
                    "can_create",
                    "can_edit",
                    "can_delete",
                    "can_view_students",
                    "can_manage_assessments",
                    "can_manage_results",
                    "can_manage_finance",
                    "can_view_reports",
                )
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Role-based access",
            {
                "fields": (
                    "user_type",
                    "phone_number",
                    "can_view",
                    "can_create",
                    "can_edit",
                    "can_delete",
                    "can_view_students",
                    "can_manage_assessments",
                    "can_manage_results",
                    "can_manage_finance",
                    "can_view_reports",
                )
            },
        ),
    )
    search_fields = ("username", "email", "first_name", "last_name")


class TrainerQualificationInline(admin.TabularInline):
    model = TrainerQualification
    extra = 0


@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_number", "is_active_assessor")
    inlines = [TrainerQualificationInline]
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_number")


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "relationship_note")
    filter_horizontal = ("students",)


@admin.register(FinanceProfile)
class FinanceProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_number")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_number")
