"""Backward-compatible re-exports — use apps.core.services for new code."""

from apps.core.services.assessment_service import (  # noqa: F401
    attachment_unit_graded,
    competency_is_competent,
    is_certificate_eligible,
    latest_attempt,
    program_units_complete,
    refresh_certificate_eligibility,
    sync_student_unit_result,
    unit_is_competent,
)
