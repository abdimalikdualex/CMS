from django.conf import settings
from django.db import models


class StudentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DEFERRED = "deferred", "Deferred"
    GRADUATED = "graduated", "Graduated"
    SUSPENDED = "suspended", "Suspended"
    DISCONTINUED = "discontinued", "Discontinued"


class IntakeMonth(models.IntegerChoices):
    JANUARY = 1, "January"
    MAY = 5, "May"
    SEPTEMBER = 9, "September"


class Intake(models.Model):
    month = models.PositiveSmallIntegerField(choices=IntakeMonth.choices)
    year = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=64, help_text='e.g. "Jan 2026"')

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "year"],
                name="unique_intake_month_year",
            )
        ]

    def __str__(self):
        return self.label


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="student_record",
        limit_choices_to={"user_type": "STUDENT"},
    )
    admission_number = models.CharField(max_length=50, unique=True, db_index=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.MALE)
    id_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="National ID or equivalent.",
    )
    passport_number = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    kcse_summary = models.TextField(
        blank=True,
        help_text="KCSE grades / summary as entered at admission.",
    )
    previous_school = models.CharField(max_length=255, blank=True)
    kcse_grade = models.CharField(max_length=10, blank=True)
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_phone = models.CharField(max_length=32, blank=True)
    guardian_relationship = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StudentStatus.choices,
        default=StudentStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["admission_number"]

    def __str__(self):
        return f"{self.admission_number} — {self.user}"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    WITHDRAWN = "withdrawn", "Withdrawn"


class StudyMode(models.TextChoices):
    FULL_TIME = "full_time", "Full-time"
    PART_TIME = "part_time", "Part-time"


class Enrollment(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    program = models.ForeignKey(
        "academics.Program",
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    intake = models.ForeignKey(
        Intake,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    campus = models.ForeignKey(
        "core.Campus",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enrollments",
    )
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
        db_index=True,
    )
    mode_of_study = models.CharField(
        max_length=20,
        choices=StudyMode.choices,
        default=StudyMode.FULL_TIME,
    )
    enrolled_on = models.DateField(auto_now_add=True)
    certificate_eligible = models.BooleanField(
        default=False,
        help_text="Set when all program competencies are met and results approved.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "program"],
                name="unique_student_program_enrollment",
            )
        ]
        ordering = ["-enrolled_on"]

    def __str__(self):
        return f"{self.student.admission_number} / {self.program.code}"


class UnitAssignment(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="unit_assignments",
    )
    unit = models.ForeignKey(
        "academics.Unit",
        on_delete=models.CASCADE,
        related_name="enrollment_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "unit"],
                name="unique_unit_assignment_per_enrollment",
            )
        ]
        ordering = ["unit__title"]

    def __str__(self):
        return f"{self.enrollment.student.admission_number} - {self.unit.title}"


class StudentDocumentType(models.TextChoices):
    ID_COPY = "id", "National ID / Passport"
    KCSE = "kcse", "KCSE certificate"
    OTHER_CERT = "certificate", "Other certificate"
    TRANSCRIPT = "transcript", "Transcript"


class StudentDocument(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=32, choices=StudentDocumentType.choices)
    file = models.FileField(upload_to="student_docs/%Y/%m/")
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.student.admission_number} — {self.get_document_type_display()}"


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class AdmissionApplication(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    id_number = models.CharField(max_length=50, blank=True)
    requested_program = models.ForeignKey(
        "academics.Program",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admission_applications",
    )
    requested_intake = models.ForeignKey(
        Intake,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admission_applications",
    )
    status = models.CharField(max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING, db_index=True)
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_admission_applications",
    )
    linked_student = models.ForeignKey(
        Student,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_applications",
    )

    class Meta:
        ordering = ["-applied_at"]

    def __str__(self):
        return f"{self.full_name} ({self.status})"
