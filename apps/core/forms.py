import re

from django import forms

from apps.academics.models import (
    CourseRegistration,
    Program,
    ShortCourse,
    ShortCourseAttendance,
    ShortCourseAssessment,
    ShortCourseCertificate,
    ShortCourseEnrollment,
    ShortCoursePayment,
    ShortCourseSession,
    ShortCoursePayment,
    Unit,
    UnitTrainerAssignment,
)
from apps.accounts.models import User, UserType
from apps.assessments.models import AssessmentAttempt
from apps.attachments.models import Placement, SupervisorEvaluation
from apps.communications.models import Announcement, InAppNotification
from apps.core.models import SystemSetting
from apps.finance.models import FeeStructure, Payment
from apps.library.models import Book, BookIssue
from apps.students.models import Enrollment, Intake, Student, StudentStatus, StudyMode
from apps.students.models import AdmissionApplication
from apps.timetable.models import AttendanceRecord, ClassSession


class UserCreateForm(forms.ModelForm):
    full_name = forms.CharField(max_length=255)
    username = forms.CharField(required=False)
    password = forms.CharField(widget=forms.PasswordInput(), min_length=6, required=False)
    auto_generate_username = forms.BooleanField(required=False, initial=True)
    auto_generate_password = forms.BooleanField(required=False, initial=True)
    role = forms.ChoiceField(
        choices=[
            (UserType.FINANCE, "Finance"),
            (UserType.ADMISSION_FINANCE, "Admission & Finance Officer"),
            (UserType.TRAINER, "Staff (Lecturer/Trainer)"),
            (UserType.ADMISSION, "Admission Officer"),
            (UserType.STUDENT, "Student"),
        ]
    )
    program = forms.ModelChoiceField(queryset=Program.objects.all(), required=False)
    intake = forms.ModelChoiceField(queryset=Intake.objects.all(), required=False)
    admission_number = forms.CharField(required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "phone_number",
            "is_active",
        ]

    def clean(self):
        cleaned = super().clean()
        auto_username = cleaned.get("auto_generate_username")
        auto_password = cleaned.get("auto_generate_password")
        username = (cleaned.get("username") or "").strip()
        password = cleaned.get("password")
        role = cleaned.get("role")
        if not auto_username and not username:
            self.add_error("username", "Provide username or enable auto-generate.")
        if not auto_password and not password:
            self.add_error("password", "Provide password or enable auto-generate.")
        if role == UserType.STUDENT:
            if not cleaned.get("program"):
                self.add_error("program", "Program is required for student role.")
            if not cleaned.get("intake"):
                self.add_error("intake", "Intake is required for student role.")
        return cleaned


class UserUpdateForm(forms.ModelForm):
    full_name = forms.CharField(max_length=255)
    role = forms.ChoiceField(
        choices=[
            (UserType.FINANCE, "Finance"),
            (UserType.ADMISSION_FINANCE, "Admission & Finance Officer"),
            (UserType.TRAINER, "Staff (Lecturer/Trainer)"),
            (UserType.ADMISSION, "Admission Officer"),
            (UserType.STUDENT, "Student"),
        ]
    )
    password = forms.CharField(widget=forms.PasswordInput(), min_length=6, required=False)

    class Meta:
        model = User
        fields = ["username", "email", "phone_number", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["full_name"].initial = self.instance.get_full_name()
            self.fields["role"].initial = self.instance.user_type


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "user",
            "admission_number",
            "gender",
            "id_number",
            "phone",
            "date_of_birth",
            "address",
            "status",
        ]


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["student", "program", "intake", "status"]


class ProgramForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course_type"].initial = "TVET_PROGRAM"
        self.fields["course_type"].widget = forms.HiddenInput()
        self.fields["level"].initial = "L4"
        self.fields["level"].widget = forms.HiddenInput()
        self.fields["duration_months"].initial = 12
        self.fields["duration_months"].widget = forms.HiddenInput()
        self.fields["total_credit_hours"].initial = 0
        self.fields["total_credit_hours"].widget = forms.HiddenInput()
        self.fields["name"].label = "Program Name"
        self.fields["code"].label = "Program Code"
        self.fields["duration_years"].label = "Duration (Years)"

    class Meta:
        model = Program
        fields = [
            "campus",
            "code",
            "name",
            "department",
            "course_type",
            "level",
            "duration_years",
            "duration_months",
            "total_credit_hours",
            "is_active",
        ]

    def clean(self):
        cleaned = super().clean()
        years = cleaned.get("duration_years") or 0
        if years <= 0:
            self.add_error("duration_years", "Duration in years must be at least 1.")
        if years:
            cleaned["duration_months"] = years * 12
            cleaned["total_credit_hours"] = cleaned.get("total_credit_hours") or 0
        return cleaned


class UnitForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].label = "Course Title"
        self.fields["code"].label = "Course Code"
        self.fields["program"].label = "Academic Program"

    class Meta:
        model = Unit
        fields = ["program", "code", "title", "credit_hours"]


class UnitTrainerAssignmentForm(forms.ModelForm):
    trainer = forms.ModelChoiceField(queryset=User.objects.filter(user_type=UserType.TRAINER))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unit"].label = "Course"
        self.fields["trainer"].label = "Lecturer"

    class Meta:
        model = UnitTrainerAssignment
        fields = ["unit", "trainer", "semester", "is_primary"]


class ShortCourseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Course Name"
        self.fields["course_code"].label = "Course Code"
        self.fields["duration_value"].label = "Duration"
        self.fields["fee_amount"].label = "Fee"
        self.fields["instructor"].label = "Lecturer"

    class Meta:
        model = ShortCourse
        fields = [
            "course_code",
            "name",
            "category",
            "description",
            "level",
            "level_label",
            "duration_value",
            "duration_unit",
            "fee_amount",
            "instructor",
            "max_capacity",
            "schedule_notes",
            "is_active",
        ]


class ShortCourseEnrollmentForm(forms.ModelForm):
    enrollment_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Enrollment Date",
    )

    class Meta:
        model = ShortCourseEnrollment
        fields = ["student", "short_course", "status", "progress_percent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["short_course"].label = "Course"
        self.fields["progress_percent"].label = "Progress (%)"

    def save(self, commit=True):
        obj = super().save(commit=False)
        enrollment_date = self.cleaned_data.get("enrollment_date")
        if enrollment_date:
            obj.enrolled_on = enrollment_date
        if commit:
            obj.save()
        return obj


class ShortCourseSessionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["short_course"].label = "Course"
        self.fields["session_time"].label = "Start Time"
        self.fields["end_time"].label = "End Time"
        self.fields["instructor"].label = "Instructor"

    class Meta:
        model = ShortCourseSession
        fields = ["short_course", "session_date", "session_time", "end_time", "location", "instructor", "status", "topic"]
        widgets = {
            "session_date": forms.DateInput(attrs={"type": "date"}),
            "session_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class ShortCourseAttendanceForm(forms.ModelForm):
    class Meta:
        model = ShortCourseAttendance
        fields = ["session", "enrollment", "status"]


class ShortCourseCertificateForm(forms.ModelForm):
    certificate_number = forms.CharField(required=False)

    class Meta:
        model = ShortCourseCertificate
        fields = ["enrollment", "certificate_number"]


class ShortCourseAssessmentForm(forms.ModelForm):
    class Meta:
        model = ShortCourseAssessment
        fields = ["enrollment", "session", "skill_rating", "outcome", "remarks", "instructor"]


class ShortCoursePaymentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enrollment"].queryset = (
            self.fields["enrollment"].queryset.select_related("student__user", "short_course")
            .order_by("-enrolled_on")
        )
        self.fields["enrollment"].label = "Enrollment"
        self.fields["enrollment"].label_from_instance = (
            lambda e: f"ENR-{e.id} | {e.student.admission_number} - "
            f"{(e.student.user.get_full_name() or e.student.user.username)} | {e.short_course.name}"
        )
        self.fields["amount"].label = "Amount Paid"
        self.fields["reference"].label = "Reference (Transaction Code)"
        self.fields["mpesa_reference"].label = "M-PESA Reference"

    class Meta:
        model = ShortCoursePayment
        fields = ["enrollment", "amount", "method", "mpesa_reference", "reference"]


class PlacementForm(forms.ModelForm):
    class Meta:
        model = Placement
        fields = [
            "enrollment",
            "company_name",
            "supervisor_name",
            "supervisor_phone",
            "supervisor_email",
            "start_date",
            "end_date",
        ]


class SupervisorEvaluationForm(forms.ModelForm):
    class Meta:
        model = SupervisorEvaluation
        fields = ["placement", "grade", "comments"]


class SystemSettingForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = ["institution_name", "academic_year", "current_semester", "intake_periods", "grading_system"]


class AdmissionApplicationForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = ["full_name", "email", "phone", "id_number", "requested_program", "requested_intake", "notes"]


class AssessmentEntryForm(forms.ModelForm):
    enrollment = forms.ModelChoiceField(queryset=Enrollment.objects.select_related("student", "program", "intake"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assessment"].queryset = self.fields["assessment"].queryset.select_related("unit").order_by(
            "unit__program__code", "unit__code", "title"
        )
        self.fields["enrollment"].label_from_instance = (
            lambda e: f"{e.student.admission_number} - {e.student.user.get_full_name() or e.student.user.username} ({e.program.code})"
        )
        self.fields["assessment"].label_from_instance = (
            lambda a: f"{a.unit.title} - {a.title} ({a.get_kind_display()})"
        )

    class Meta:
        model = AssessmentAttempt
        fields = ["enrollment", "assessment", "score", "comments"]

    def clean_score(self):
        score = self.cleaned_data.get("score")
        if score is None:
            raise forms.ValidationError("Score is required.")
        if score < 0:
            raise forms.ValidationError("Score cannot be negative.")
        return score


class PaymentEntryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice"].queryset = self.fields["invoice"].queryset.exclude(status="paid").select_related("student")

    class Meta:
        model = Payment
        fields = ["invoice", "amount", "method", "transaction_code", "reference", "paid_on"]

    def clean(self):
        cleaned = super().clean()
        invoice = cleaned.get("invoice")
        amount = cleaned.get("amount")
        if invoice and amount is not None:
            if amount <= 0:
                self.add_error("amount", "Payment amount must be greater than zero.")
            if amount > invoice.balance:
                self.add_error("amount", f"Amount cannot exceed invoice balance ({invoice.balance}).")
        return cleaned


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = [
            "program",
            "name",
            "tuition_fee",
            "registration_fee",
            "other_charges",
            "discount_amount",
            "is_active",
            "effective_from",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
        }


class StudentAdmissionForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    admission_number = forms.CharField(max_length=50, required=False)
    gender = forms.ChoiceField(choices=Student.Gender.choices)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    id_number = forms.CharField(max_length=50)
    passport_number = forms.CharField(max_length=50, required=False)
    phone = forms.CharField(max_length=32)
    email = forms.EmailField(required=False)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    short_course = forms.ModelChoiceField(
        queryset=ShortCourse.objects.filter(is_active=True).order_by("name"),
        required=False,
        label="Course",
    )
    initial_payment = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, initial=0)
    program = forms.ModelChoiceField(queryset=Program.objects.filter(is_active=True).order_by("code"), required=False)
    intake = forms.ModelChoiceField(queryset=Intake.objects.all(), required=False)
    mode_of_study = forms.ChoiceField(choices=StudyMode.choices, initial=StudyMode.FULL_TIME)
    status = forms.ChoiceField(choices=StudentStatus.choices, initial=StudentStatus.ACTIVE)
    guardian_name = forms.CharField(max_length=255, required=False)
    guardian_phone = forms.CharField(max_length=32, required=False)
    guardian_relationship = forms.CharField(max_length=64, required=False)
    previous_school = forms.CharField(max_length=255, required=False)
    kcse_grade = forms.CharField(max_length=10, required=False)
    id_document = forms.FileField(required=False)
    certificate_document = forms.FileField(required=False)
    discount_amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)

    def clean_id_number(self):
        value = (self.cleaned_data.get("id_number") or "").strip()
        if not value:
            raise forms.ValidationError("ID number is required.")
        if Student.objects.filter(id_number__iexact=value).exists():
            raise forms.ValidationError("A student with this ID number already exists.")
        return value

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not re.fullmatch(r"^\+?[0-9]{9,15}$", phone):
            raise forms.ValidationError("Phone number must be 9-15 digits (optional leading +).")
        return phone

    def clean_guardian_phone(self):
        phone = (self.cleaned_data.get("guardian_phone") or "").strip()
        if phone and not re.fullmatch(r"^\+?[0-9]{9,15}$", phone):
            raise forms.ValidationError("Guardian phone must be 9-15 digits (optional leading +).")
        return phone


class ClassSessionForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ["unit", "trainer", "room", "starts_at", "ends_at"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ["session", "student", "status"]


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "total_copies", "available_copies"]


class BookIssueForm(forms.ModelForm):
    class Meta:
        model = BookIssue
        fields = ["book", "student", "issued_on", "due_on"]
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "due_on": forms.DateInput(attrs={"type": "date"}),
        }


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body", "audience", "program", "intake", "published_at"]
        widgets = {
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class InAppNotificationForm(forms.ModelForm):
    class Meta:
        model = InAppNotification
        fields = ["recipient", "title", "message", "is_read"]


class CourseRegistrationForm(forms.ModelForm):
    class Meta:
        model = CourseRegistration
        fields = ["unit", "semester", "status"]

