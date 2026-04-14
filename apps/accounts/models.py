from django.contrib.auth.models import AbstractUser
from django.db import models


class UserType(models.TextChoices):
    ADMIN = "ADMIN", "Administrator"
    ADMISSION = "ADMISSION", "Admission Officer"
    ADMISSION_FINANCE = "ADMISSION_FINANCE", "Admission & Finance Officer"
    TRAINER = "TRAINER", "Lecturer"
    FINANCE = "FINANCE", "Finance"
    STUDENT = "STUDENT", "Student"
    PARENT = "PARENT", "Parent"


class User(AbstractUser):
    email = models.EmailField("email address", unique=True, blank=True)
    phone_number = models.CharField(max_length=32, blank=True)
    user_type = models.CharField(
        max_length=32,
        choices=UserType.choices,
        default=UserType.STUDENT,
        db_index=True,
    )
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_view_students = models.BooleanField(default=False)
    can_manage_assessments = models.BooleanField(default=False)
    can_manage_results = models.BooleanField(default=False)
    can_manage_finance = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_user_type_display()})"

    def has_panel_permission(self, attr_name: str) -> bool:
        if self.is_superuser:
            return True
        return bool(getattr(self, attr_name, False))

    def apply_role_permissions(self):
        if self.is_superuser:
            self.can_view = True
            self.can_create = True
            self.can_edit = True
            self.can_delete = True
            self.can_view_students = True
            self.can_manage_assessments = True
            self.can_manage_results = True
            self.can_manage_finance = True
            self.can_view_reports = True
            return
        defaults = {
            UserType.ADMIN: dict(
                can_view=False,
                can_create=False,
                can_edit=False,
                can_delete=False,
                can_view_students=False,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=False,
                can_view_reports=False,
            ),
            UserType.ADMISSION: dict(
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=False,
                can_view_students=True,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=False,
                can_view_reports=False,
            ),
            UserType.ADMISSION_FINANCE: dict(
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=False,
                can_view_students=True,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=True,
                can_view_reports=True,
            ),
            UserType.TRAINER: dict(
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=False,
                can_view_students=False,
                can_manage_assessments=True,
                can_manage_results=True,
                can_manage_finance=False,
                can_view_reports=False,
            ),
            UserType.FINANCE: dict(
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=False,
                can_view_students=False,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=True,
                can_view_reports=True,
            ),
            UserType.STUDENT: dict(
                can_view=True,
                can_create=False,
                can_edit=False,
                can_delete=False,
                can_view_students=False,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=False,
                can_view_reports=False,
            ),
            UserType.PARENT: dict(
                can_view=False,
                can_create=False,
                can_edit=False,
                can_delete=False,
                can_view_students=False,
                can_manage_assessments=False,
                can_manage_results=False,
                can_manage_finance=False,
                can_view_reports=False,
            ),
        }
        values = defaults.get(self.user_type, defaults[UserType.STUDENT])
        for key, val in values.items():
            setattr(self, key, val)


class TrainerProfile(models.Model):
    """TVETA-style trainer record: qualifications and assessor eligibility."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="trainer_profile",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    employee_number = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    is_active_assessor = models.BooleanField(
        default=True,
        help_text="If false, user cannot record assessments regardless of unit assignment.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Trainer: {self.user}"


class TrainerQualification(models.Model):
    trainer = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name="qualifications",
    )
    name = models.CharField(max_length=255)
    awarding_body = models.CharField(max_length=255, blank=True)
    document = models.FileField(upload_to="trainer_qualifications/%Y/%m/", blank=True)
    obtained_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-obtained_on", "name"]

    def __str__(self):
        return f"{self.name} ({self.trainer})"


class ParentProfile(models.Model):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="parent_profile",
        limit_choices_to={"user_type": UserType.PARENT},
    )
    students = models.ManyToManyField("students.Student", related_name="parent_profiles", blank=True)
    phone = models.CharField(max_length=32, blank=True)
    relationship_note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Parent: {self.user.username}"


class FinanceProfile(models.Model):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="finance_profile",
        limit_choices_to={"user_type": UserType.FINANCE},
    )
    employee_number = models.CharField(max_length=50, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Finance: {self.user.username}"
