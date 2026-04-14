from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.academics.models import CompetencyUnit, Unit


class AssessmentKind(models.TextChoices):
    CAT = "cat", "CAT"
    MAIN = "main", "Main Exam"
    PRACTICAL = "practical", "Practical"
    THEORY = "theory", "Theory"
    INDUSTRIAL_ATTACHMENT = "industrial_attachment", "Industrial attachment"


class CompetencyGrade(models.TextChoices):
    COMPETENT = "C", "Competent"
    NOT_YET = "NYC", "Not Yet Competent"


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    PUBLISHED = "published", "Published"


class Assessment(models.Model):
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    competency = models.ForeignKey(
        CompetencyUnit,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    kind = models.CharField(max_length=32, choices=AssessmentKind.choices)
    title = models.CharField(max_length=255)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    pass_mark = models.DecimalField(max_digits=6, decimal_places=2, default=50)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["unit", "competency", "kind"]

    def clean(self):
        if self.competency.unit_id != self.unit_id:
            raise ValidationError("Assessment unit must match competency unit.")

    def __str__(self):
        return f"{self.title} ({self.get_kind_display()})"


class AssessmentAttempt(models.Model):
    class LetterGrade(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"
        F = "F", "F"

    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="assessment_attempts",
    )
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    grade = models.CharField(
        max_length=8,
        choices=CompetencyGrade.choices,
        blank=True,
    )
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_attempts",
    )
    comments = models.TextField(blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    letter_grade = models.CharField(max_length=2, choices=LetterGrade.choices, blank=True)
    is_pass = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "assessment", "attempt_number"],
                name="unique_attempt_number_per_enrollment_assessment",
            )
        ]

    def clean(self):
        from apps.accounts.models import UserType
        from apps.academics.models import UnitTrainerAssignment

        if not (self.assessor.is_superuser or self.assessor.user_type == UserType.TRAINER):
            raise ValidationError({"assessor": "Only lecturer users may record exam marks."})
        unit = self.assessment.unit
        if self.assessor.user_type == UserType.TRAINER:
            allowed = UnitTrainerAssignment.objects.filter(
                unit=unit,
                trainer=self.assessor,
            ).exists()
            if not allowed:
                raise ValidationError(
                    {"assessor": "This lecturer is not assigned to this course."}
                )
        if self.enrollment.program_id != unit.program_id:
            raise ValidationError({"enrollment": "Selected enrollment does not belong to this unit's program."})
        if self.score is not None:
            if self.score < 0:
                raise ValidationError({"score": "Score cannot be negative."})
            if self.score > self.assessment.max_score:
                raise ValidationError({"score": f"Score cannot exceed max score ({self.assessment.max_score})."})

    def save(self, *args, **kwargs):
        def _letter(score_value):
            if score_value >= 80:
                return self.LetterGrade.A
            if score_value >= 70:
                return self.LetterGrade.B
            if score_value >= 60:
                return self.LetterGrade.C
            if score_value >= 50:
                return self.LetterGrade.D
            return self.LetterGrade.F

        if not self.pk:
            latest = (
                AssessmentAttempt.objects.filter(enrollment=self.enrollment, assessment=self.assessment)
                .order_by("-attempt_number")
                .first()
            )
            self.attempt_number = (latest.attempt_number + 1) if latest else 1
        if self.score is not None:
            self.is_pass = self.score >= self.assessment.pass_mark
            self.letter_grade = _letter(float(self.score))
            self.grade = CompetencyGrade.COMPETENT if self.is_pass else CompetencyGrade.NOT_YET
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enrollment} — {self.assessment} (#{self.attempt_number})"


class AssessmentEvidence(models.Model):
    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="evidence_files",
    )
    file = models.FileField(upload_to="assessment_evidence/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence for attempt {self.attempt_id}"


class StudentUnitResult(models.Model):
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="unit_results",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="student_results",
    )
    overall_grade = models.CharField(
        max_length=8,
        choices=CompetencyGrade.choices,
        blank=True,
        help_text="C only when all competencies in the unit are met with evidence.",
    )
    publication_status = models.CharField(
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "unit"],
                name="unique_student_unit_result",
            )
        ]

    def __str__(self):
        return f"{self.enrollment} — {self.unit.code}: {self.overall_grade or '—'}"


class Result(models.Model):
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="results",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="results",
    )
    final_status = models.CharField(
        max_length=8,
        choices=CompetencyGrade.choices,
        default=CompetencyGrade.NOT_YET,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "unit"],
                name="unique_student_result_per_unit",
            )
        ]

    def __str__(self):
        return f"{self.student.admission_number} — {self.unit.code}: {self.final_status}"
