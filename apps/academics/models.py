from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.accounts.models import UserType


class ProgramLevel(models.TextChoices):
    LEVEL_4 = "L4", "TVET Level 4"
    LEVEL_5 = "L5", "TVET Level 5"
    LEVEL_6 = "L6", "TVET Level 6"


class CourseType(models.TextChoices):
    TVET_PROGRAM = "TVET_PROGRAM", "TVET Program"
    SHORT_COURSE = "SHORT_COURSE", "Short Course"


class Program(models.Model):
    campus = models.ForeignKey(
        "core.Campus",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="programs",
    )
    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    course_type = models.CharField(
        max_length=20,
        choices=CourseType.choices,
        default=CourseType.TVET_PROGRAM,
        db_index=True,
    )
    level = models.CharField(max_length=8, choices=ProgramLevel.choices, db_index=True)
    department = models.CharField(max_length=120, blank=True)
    duration_years = models.PositiveSmallIntegerField(default=1)
    duration_months = models.PositiveSmallIntegerField()
    total_credit_hours = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Academic Program"
        verbose_name_plural = "Academic Programs"

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.duration_years and not self.duration_months:
            self.duration_months = int(self.duration_years) * 12
        elif self.duration_years:
            self.duration_months = int(self.duration_years) * 12
        super().save(*args, **kwargs)


class UnitKind(models.TextChoices):
    CORE = "core", "Core"
    ELECTIVE = "elective", "Elective"


class Unit(models.Model):
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="units",
    )
    code = models.CharField(max_length=32, db_index=True)
    title = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=UnitKind.choices, default=UnitKind.CORE)
    credit_hours = models.PositiveSmallIntegerField()
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="required_for")

    class Meta:
        ordering = ["program", "code"]
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        constraints = [
            models.UniqueConstraint(
                fields=["program", "code"],
                name="unique_unit_code_per_program",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.program.code})"


class RegistrationStatus(models.TextChoices):
    REGISTERED = "registered", "Registered"
    DROPPED = "dropped", "Dropped"


class Semester(models.TextChoices):
    SEM1 = "S1", "Semester 1"
    SEM2 = "S2", "Semester 2"


class CourseRegistration(models.Model):
    enrollment = models.ForeignKey(
        "students.Enrollment",
        on_delete=models.CASCADE,
        related_name="course_registrations",
    )
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="registrations")
    semester = models.CharField(max_length=8, choices=Semester.choices, default=Semester.SEM1)
    status = models.CharField(max_length=16, choices=RegistrationStatus.choices, default=RegistrationStatus.REGISTERED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "unit", "semester"],
                name="unique_unit_registration_per_semester",
            )
        ]

    def clean(self):
        if self.enrollment.program_id != self.unit.program_id:
            raise ValidationError("Selected unit does not belong to the student's enrolled program.")

    def __str__(self):
        return f"{self.enrollment.student.admission_number} - {self.unit.title} ({self.semester})"


class LearningOutcome(models.Model):
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="learning_outcomes",
    )
    code = models.CharField(max_length=32)
    description = models.TextField()

    class Meta:
        ordering = ["unit", "code"]

    def __str__(self):
        return f"{self.code}: {self.unit.code}"


class CompetencyUnit(models.Model):
    """Smallest CBET assessable unit of competence within a module/unit."""

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="competencies",
    )
    code = models.CharField(max_length=32)
    statement = models.TextField()

    class Meta:
        ordering = ["unit", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "code"],
                name="unique_competency_code_per_unit",
            )
        ]

    def __str__(self):
        return f"{self.code} — {self.unit.code}"


class UnitTrainerAssignment(models.Model):
    class SemesterChoice(models.TextChoices):
        SEM1 = "S1", "Semester 1"
        SEM2 = "S2", "Semester 2"
        SEM3 = "S3", "Semester 3"

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="trainer_assignments",
    )
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="unit_assignments",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    semester = models.CharField(max_length=8, choices=SemesterChoice.choices, default=SemesterChoice.SEM1)
    is_primary = models.BooleanField(default=False)
    can_assess = models.BooleanField(
        default=True,
        help_text="Deprecated: retained for compatibility.",
    )

    class Meta:
        verbose_name = "Lecturer Assignment"
        verbose_name_plural = "Lecturer Assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "trainer"],
                name="unique_trainer_per_unit",
            )
        ]

    def __str__(self):
        return f"{self.trainer} -> {self.unit.code} ({self.get_semester_display()})"


class DurationUnit(models.TextChoices):
    DAYS = "days", "Days"
    WEEKS = "weeks", "Weeks"
    MONTHS = "months", "Months"


class ShortCourse(models.Model):
    class Category(models.TextChoices):
        ICT = "ict", "ICT"
        LANGUAGE = "language", "Language"
        SKILL = "skill", "Skill"

    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    course_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    name = models.CharField(max_length=255, db_index=True)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.ICT, db_index=True)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.BEGINNER)
    level_label = models.CharField(max_length=64, blank=True, help_text="e.g. Beginner, Intermediate, Advanced")
    duration_value = models.PositiveSmallIntegerField(default=1)
    duration_unit = models.CharField(max_length=16, choices=DurationUnit.choices, default=DurationUnit.WEEKS)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="short_courses",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    max_capacity = models.PositiveIntegerField(null=True, blank=True)
    schedule_notes = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "level_label"]
        verbose_name = "Course"
        verbose_name_plural = "Courses"

    def __str__(self):
        return f"{self.name} {self.level_label}".strip()

    def save(self, *args, **kwargs):
        if not self.course_code:
            base = "".join(ch for ch in self.name.upper() if ch.isalnum())[:6] or "ICT"
            candidate = f"{base}-{self.duration_value}"
            counter = 1
            while ShortCourse.objects.exclude(pk=self.pk).filter(course_code=candidate).exists():
                counter += 1
                candidate = f"{base}-{self.duration_value}-{counter}"
            self.course_code = candidate
        if not self.level_label:
            self.level_label = self.get_level_display()
        super().save(*args, **kwargs)


class ShortCourseEnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    DROPPED = "dropped", "Dropped"


class ShortCoursePaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PARTIAL = "partial", "Partial"
    PAID = "paid", "Paid"


class ShortCourseEnrollment(models.Model):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="short_course_enrollments")
    short_course = models.ForeignKey(ShortCourse, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=16, choices=ShortCourseEnrollmentStatus.choices, default=ShortCourseEnrollmentStatus.ACTIVE)
    enrolled_on = models.DateField(default=timezone.localdate)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=16, choices=ShortCoursePaymentStatus.choices, default=ShortCoursePaymentStatus.PENDING)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-enrolled_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "short_course"],
                name="unique_student_short_course_enrollment",
            )
        ]

    def clean(self):
        if self.short_course.max_capacity:
            current = ShortCourseEnrollment.objects.filter(
                short_course=self.short_course, status=ShortCourseEnrollmentStatus.ACTIVE
            )
            if self.pk:
                current = current.exclude(pk=self.pk)
            if current.count() >= self.short_course.max_capacity:
                raise ValidationError("Short course has reached maximum capacity.")

    def save(self, *args, **kwargs):
        total = self.short_course.fee_amount or 0
        paid = self.paid_amount or 0
        if paid < 0:
            paid = 0
        if paid > total:
            paid = total
        self.paid_amount = paid
        self.balance = total - paid
        if self.balance <= 0:
            self.payment_status = ShortCoursePaymentStatus.PAID
        elif paid > 0:
            self.payment_status = ShortCoursePaymentStatus.PARTIAL
        else:
            self.payment_status = ShortCoursePaymentStatus.PENDING
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.admission_number} -> {self.short_course}"


class ShortCourseSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    short_course = models.ForeignKey(ShortCourse, on_delete=models.CASCADE, related_name="sessions")
    session_date = models.DateField()
    session_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, help_text="Room name or online meeting link")
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="short_course_sessions",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    topic = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-session_date", "-id"]

    def __str__(self):
        return f"{self.short_course} @ {self.session_date}"

    def clean(self):
        if not self.session_time:
            raise ValidationError("Start time is required.")
        if not self.end_time:
            raise ValidationError("End time is required.")
        if self.end_time <= self.session_time:
            raise ValidationError("End time must be after start time.")

        base_qs = ShortCourseSession.objects.filter(session_date=self.session_date).exclude(pk=self.pk)
        if self.status == self.Status.CANCELLED:
            return
        base_qs = base_qs.exclude(status=self.Status.CANCELLED)

        def overlaps(row):
            if not row.session_time or not row.end_time:
                return False
            return self.session_time < row.end_time and self.end_time > row.session_time

        if self.instructor_id:
            for row in base_qs.filter(instructor_id=self.instructor_id):
                if overlaps(row):
                    raise ValidationError("This instructor already has an overlapping session.")
        for row in base_qs.filter(short_course_id=self.short_course_id):
            if overlaps(row):
                raise ValidationError("This course already has an overlapping session.")

    def save(self, *args, **kwargs):
        if not self.instructor and self.short_course_id:
            self.instructor = self.short_course.instructor
        super().save(*args, **kwargs)


class ShortCourseAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"

    session = models.ForeignKey(ShortCourseSession, on_delete=models.CASCADE, related_name="attendance")
    enrollment = models.ForeignKey(ShortCourseEnrollment, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PRESENT)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-marked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "enrollment"],
                name="unique_short_course_attendance_session_enrollment",
            )
        ]

    def clean(self):
        if self.enrollment.short_course_id != self.session.short_course_id:
            raise ValidationError("Attendance enrollment must belong to session short course.")

    def __str__(self):
        return f"{self.enrollment} - {self.status}"


class ShortCourseCertificate(models.Model):
    enrollment = models.OneToOneField(
        ShortCourseEnrollment,
        on_delete=models.CASCADE,
        related_name="certificate",
    )
    certificate_number = models.CharField(max_length=64, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.certificate_number} - {self.enrollment}"


class ShortCourseAssessment(models.Model):
    class Outcome(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    enrollment = models.ForeignKey(
        ShortCourseEnrollment,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    session = models.ForeignKey(
        ShortCourseSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
    )
    skill_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Score between 1 and 100",
    )
    outcome = models.CharField(max_length=8, choices=Outcome.choices, blank=True)
    remarks = models.TextField(blank=True)
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="short_course_assessments",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assessed_at"]

    def clean(self):
        if self.skill_rating is not None and (self.skill_rating < 1 or self.skill_rating > 100):
            raise ValidationError("Skill rating must be between 1 and 100.")
        if self.session_id and self.session.short_course_id != self.enrollment.short_course_id:
            raise ValidationError("Session course must match enrollment course.")

    def save(self, *args, **kwargs):
        if self.skill_rating is not None and not self.outcome:
            self.outcome = self.Outcome.PASS if self.skill_rating >= 50 else self.Outcome.FAIL
        if not self.instructor and self.enrollment_id:
            self.instructor = self.enrollment.short_course.instructor
        super().save(*args, **kwargs)


class ShortCoursePayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        MPESA = "mpesa", "M-Pesa"

    enrollment = models.ForeignKey(
        ShortCourseEnrollment,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.MPESA)
    mpesa_reference = models.CharField(max_length=120, blank=True, db_index=True)
    reference = models.CharField(max_length=255, blank=True)
    paid_on = models.DateField(auto_now_add=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-recorded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["mpesa_reference"],
                condition=~models.Q(mpesa_reference=""),
                name="unique_short_course_mpesa_reference",
            )
        ]

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        if self.enrollment_id:
            remaining_balance = self.enrollment.balance or 0
            if self.pk:
                previous_amount = (
                    ShortCoursePayment.objects.filter(pk=self.pk).values_list("amount", flat=True).first() or 0
                )
                remaining_balance += previous_amount
            if self.amount > remaining_balance:
                raise ValidationError("Payment cannot exceed remaining enrollment balance.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        total_paid = self.enrollment.payments.aggregate(s=models.Sum("amount"))["s"] or 0
        self.enrollment.paid_amount = total_paid
        self.enrollment.save(update_fields=["paid_amount", "balance", "payment_status"])
