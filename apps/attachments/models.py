from django.db import models

from apps.assessments.models import CompetencyGrade


class Placement(models.Model):
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="placements",
    )
    company_name = models.CharField(max_length=255)
    supervisor_name = models.CharField(max_length=255)
    supervisor_phone = models.CharField(max_length=64, blank=True)
    supervisor_email = models.EmailField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.company_name} — {self.enrollment}"


class LogbookEntry(models.Model):
    placement = models.ForeignKey(
        Placement,
        on_delete=models.CASCADE,
        related_name="logbook_entries",
    )
    period_label = models.CharField(
        max_length=64,
        help_text='e.g. "Week 3" or "Jan 2026 — W1"',
    )
    activities = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["placement", "created_at"]

    def __str__(self):
        return f"{self.placement} — {self.period_label}"


class SupervisorEvaluation(models.Model):
    placement = models.ForeignKey(
        Placement,
        on_delete=models.CASCADE,
        related_name="evaluations",
    )
    grade = models.CharField(max_length=8, choices=CompetencyGrade.choices)
    comments = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evaluation {self.placement_id} — {self.grade}"
