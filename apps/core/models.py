from django.db import models


class SystemSetting(models.Model):
    institution_name = models.CharField(max_length=255, default="College Management System")
    academic_year = models.CharField(max_length=32, default="2026")
    current_semester = models.CharField(max_length=32, default="Semester 1")
    intake_periods = models.CharField(
        max_length=255,
        default="January, May, September",
        help_text="Comma-separated intake periods.",
    )
    grading_system = models.TextField(
        default="A:80-100,B:70-79,C:60-69,D:50-59,F:0-49",
        help_text="Simple grade scale definition.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.institution_name} ({self.academic_year})"


class Campus(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ApprovalType(models.TextChoices):
    RESULTS_PUBLISH = "results_publish", "Results Publish"
    FINANCE_ADJUSTMENT = "finance_adjustment", "Finance Adjustment"


class ApprovalTask(models.Model):
    task_type = models.CharField(max_length=64, choices=ApprovalType.choices)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_reviews",
    )
    status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    note = models.TextField(blank=True)
    reviewed_note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_type} ({self.status})"


class AuditLog(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=255)
    module = models.CharField(max_length=100, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=16, blank=True)
    status_code = models.PositiveSmallIntegerField(default=200)
    ip_address = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.module}:{self.action} ({self.status_code})"
