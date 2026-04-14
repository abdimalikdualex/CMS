from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from apps.accounts.models import UserType


def _deny(request, message: str):
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)
    messages.error(request, message)
    return redirect("dashboard")


def role_required(*allowed: str):
    """View decorator: allow only given user_type values (e.g. UserType.ADMIN)."""

    allowed_values = {a if isinstance(a, str) else getattr(a, "value", a) for a in allowed}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _deny(request, "Please log in to continue.")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if getattr(request.user, "user_type", None) not in allowed_values:
                return _deny(request, "You do not have access to that page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def admin_required(view_func):
    return super_admin_required(view_func)


def super_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _deny(request, "Please log in to continue.")
        if not request.user.is_superuser:
            return _deny(request, "Only Super Admin can access that page.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def trainer_required(view_func):
    return role_required(UserType.TRAINER)(view_func)


def finance_required(view_func):
    return role_required(UserType.FINANCE)(view_func)


def student_required(view_func):
    return role_required(UserType.STUDENT)(view_func)


def permission_required(permission_attr: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _deny(request, "Please log in to continue.")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if not getattr(request.user, permission_attr, False):
                return _deny(request, "You do not have required permission for that page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
