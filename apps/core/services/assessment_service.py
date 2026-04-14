"""
TVET competency roll-up, program completion, certificate eligibility.
"""

from __future__ import annotations

from apps.academics.models import CompetencyUnit, Unit
from apps.assessments.models import (
    Assessment,
    AssessmentAttempt,
    CompetencyGrade,
    PublicationStatus,
    Result,
    StudentUnitResult,
)
from apps.students.models import Enrollment, Student


def latest_attempt(enrollment_id: int, assessment_id: int) -> AssessmentAttempt | None:
    return (
        AssessmentAttempt.objects.filter(
            enrollment_id=enrollment_id,
            assessment_id=assessment_id,
        )
        .order_by("-attempt_number")
        .first()
    )


def competency_is_competent(enrollment: Enrollment, competency: CompetencyUnit) -> bool:
    """
    A competency is Competent when every required assessment has latest grade C
    and at least one evidence file on that latest attempt.
    """
    assessments = Assessment.objects.filter(
        competency=competency,
        is_required=True,
    )
    if not assessments.exists():
        return False

    for a in assessments:
        att = latest_attempt(enrollment.pk, a.pk)
        if att is None:
            return False
        if att.grade != CompetencyGrade.COMPETENT:
            return False
        if not att.evidence_files.exists():
            return False
    return True


def unit_is_competent(enrollment: Enrollment, unit: Unit) -> bool:
    competencies = unit.competencies.all()
    if not competencies.exists():
        return False
    for c in competencies:
        if not competency_is_competent(enrollment, c):
            return False
    return True


def sync_student_unit_result(enrollment: Enrollment, unit: Unit) -> StudentUnitResult:
    """Recompute overall unit grade from attempts; keeps row for publication workflow."""
    overall = (
        CompetencyGrade.COMPETENT
        if unit_is_competent(enrollment, unit)
        else CompetencyGrade.NOT_YET
    )
    obj, _ = StudentUnitResult.objects.update_or_create(
        enrollment=enrollment,
        unit=unit,
        defaults={"overall_grade": overall},
    )
    update_student_result(enrollment.student, unit)
    return obj


def program_units_complete(enrollment: Enrollment) -> bool:
    program = enrollment.program
    units = program.units.all()
    for unit in units:
        if not unit_is_competent(enrollment, unit):
            return False
    return units.exists()


def attachment_unit_graded(enrollment: Enrollment) -> bool:
    """Industrial attachment assessments (if any) must be C with evidence."""
    from apps.assessments.models import AssessmentKind

    ia = Assessment.objects.filter(
        unit__program=enrollment.program,
        kind=AssessmentKind.INDUSTRIAL_ATTACHMENT,
    )
    if not ia.exists():
        return True
    for assessment in ia:
        att = latest_attempt(enrollment.pk, assessment.pk)
        if att is None or att.grade != CompetencyGrade.COMPETENT:
            return False
        if not att.evidence_files.exists():
            return False
    return True


def is_certificate_eligible(enrollment: Enrollment) -> bool:
    """All program units competent, published, and industrial attachment (if any) passed."""
    units = list(enrollment.program.units.all())
    if not units:
        return False
    for unit in units:
        if not unit_is_competent(enrollment, unit):
            return False
        result = StudentUnitResult.objects.filter(
            enrollment=enrollment,
            unit=unit,
            publication_status=PublicationStatus.PUBLISHED,
            overall_grade=CompetencyGrade.COMPETENT,
        ).first()
        if not result:
            return False
    if not attachment_unit_graded(enrollment):
        return False
    return True


def refresh_certificate_eligibility(enrollment: Enrollment) -> bool:
    ok = is_certificate_eligible(enrollment)
    Enrollment.objects.filter(pk=enrollment.pk).update(certificate_eligible=ok)
    enrollment.certificate_eligible = ok
    return ok


def calculate_final_result(enrollment: Enrollment, unit: Unit) -> str:
    """Latest competency roll-up for a unit (C or NYC)."""
    sync_student_unit_result(enrollment, unit)
    r = StudentUnitResult.objects.filter(enrollment=enrollment, unit=unit).first()
    return r.overall_grade if r and r.overall_grade else CompetencyGrade.NOT_YET


def update_student_result(student: Student, unit: Unit) -> Result:
    """
    MVP result roll-up:
    latest attempt (for this student+unit) determines final status C/NYC.
    """
    latest = (
        AssessmentAttempt.objects.filter(
            enrollment__student=student,
            assessment__unit=unit,
        )
        .order_by("-attempt_number", "-recorded_at")
        .first()
    )
    status = (
        CompetencyGrade.COMPETENT
        if latest and latest.grade == CompetencyGrade.COMPETENT
        else CompetencyGrade.NOT_YET
    )
    obj, _ = Result.objects.update_or_create(
        student=student,
        unit=unit,
        defaults={"final_status": status},
    )
    return obj
