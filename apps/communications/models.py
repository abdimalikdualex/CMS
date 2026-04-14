from django.conf import settings
from django.db import models


class AnnouncementAudience(models.TextChoices):
    ALL_STUDENTS = "all_students", "All students"
    PROGRAM = "program", "Specific program"
    INTAKE = "intake", "Specific intake"


class Announcement(models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField()
    audience = models.CharField(
        max_length=32,
        choices=AnnouncementAudience.choices,
        default=AnnouncementAudience.ALL_STUDENTS,
    )
    program = models.ForeignKey(
        "academics.Program",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    intake = models.ForeignKey(
        "students.Intake",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_created",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", "In-app only"
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"


class NotificationTemplate(models.Model):
    """MVP-lite hooks for fee reminders, results, admission — wire to tasks later."""

    key = models.SlugField(unique=True)
    description = models.CharField(max_length=255)
    default_channel = models.CharField(
        max_length=16,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
    )

    def __str__(self):
        return self.key


class InAppNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient} - {self.title}"
