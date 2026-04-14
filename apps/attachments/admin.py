from django.contrib import admin

from .models import LogbookEntry, Placement, SupervisorEvaluation


class LogbookEntryInline(admin.TabularInline):
    model = LogbookEntry
    extra = 0


class SupervisorEvaluationInline(admin.TabularInline):
    model = SupervisorEvaluation
    extra = 0


@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    list_display = ("company_name", "enrollment", "start_date", "end_date")
    inlines = [LogbookEntryInline, SupervisorEvaluationInline]
