from django.contrib import admin

from .models import AttendanceRecord, ClassSession, Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity")


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ("unit", "trainer", "room", "starts_at", "ends_at")
    list_filter = ("unit__program",)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("session", "student", "status", "marked_at")
    list_filter = ("status", "marked_at")
