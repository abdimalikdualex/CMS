from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import UserType


class Room(models.Model):
    name = models.CharField(max_length=128)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClassSession(models.Model):
    unit = models.ForeignKey(
        "academics.Unit",
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="class_sessions",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at"]

    def clean(self):
        if self.ends_at <= self.starts_at:
            raise ValidationError("Session end must be after start.")
        trainer_clash = ClassSession.objects.filter(
            trainer=self.trainer,
            starts_at__lt=self.ends_at,
            ends_at__gt=self.starts_at,
        )
        if self.pk:
            trainer_clash = trainer_clash.exclude(pk=self.pk)
        if trainer_clash.exists():
            raise ValidationError("Trainer has a conflicting session.")
        if self.room_id:
            room_clash = ClassSession.objects.filter(
                room=self.room,
                starts_at__lt=self.ends_at,
                ends_at__gt=self.starts_at,
            )
            if self.pk:
                room_clash = room_clash.exclude(pk=self.pk)
            if room_clash.exists():
                raise ValidationError("Room has a conflicting session.")

    def __str__(self):
        return f"{self.unit.code} @ {self.starts_at}"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    LATE = "late", "Late"
    ABSENT = "absent", "Absent"


class AttendanceRecord(models.Model):
    session = models.ForeignKey(
        ClassSession,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(max_length=16, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="unique_attendance_per_session_student")
        ]
        ordering = ["-marked_at"]

    def clean(self):
        if self.student.enrollments.filter(program=self.session.unit.program).exists() is False:
            raise ValidationError("Student is not enrolled in this session's program.")

    def __str__(self):
        return f"{self.student.admission_number} - {self.session.unit.code} ({self.status})"
