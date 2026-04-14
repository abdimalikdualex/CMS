"""Role helpers for views and templates."""

from apps.accounts.models import UserType


def is_admin(user) -> bool:
    return bool(user.is_authenticated and getattr(user, "is_superuser", False))


def is_trainer(user) -> bool:
    return bool(user.is_authenticated and getattr(user, "user_type", None) == UserType.TRAINER)


def is_finance(user) -> bool:
    return bool(
        user.is_authenticated
        and getattr(user, "user_type", None) in {UserType.FINANCE, UserType.ADMISSION_FINANCE}
    )


def is_admission(user) -> bool:
    return bool(
        user.is_authenticated
        and getattr(user, "user_type", None) in {UserType.ADMISSION, UserType.ADMISSION_FINANCE}
    )


def is_student(user) -> bool:
    return bool(user.is_authenticated and getattr(user, "user_type", None) == UserType.STUDENT)


def is_parent(user) -> bool:
    return bool(user.is_authenticated and getattr(user, "user_type", None) == UserType.PARENT)
