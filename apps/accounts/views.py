from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User, UserType
from apps.core.models import AuditLog


def _redirect_url_for_user(user) -> str:
    if user.is_superuser:
        return reverse("admin_dashboard")
    mapping = {
        UserType.ADMISSION: "admission_dashboard",
        UserType.ADMISSION_FINANCE: "admission_finance_dashboard",
        UserType.TRAINER: "trainer_dashboard",
        UserType.FINANCE: "finance_dashboard",
        UserType.STUDENT: "student_dashboard",
        UserType.PARENT: "parent_dashboard",
    }
    name = mapping.get(getattr(user, "user_type", None), "student_dashboard")
    return reverse(name)


def _authenticate_flexible(request, identifier: str, password: str):
    ident = (identifier or "").strip()
    if not ident or password is None:
        return None

    username_candidates = [ident]
    matched_usernames = (
        User.objects.filter(
            Q(username__iexact=ident)
            | Q(email__iexact=ident)
            | Q(student_record__admission_number__iexact=ident)
        )
        .values_list("username", flat=True)
        .distinct()[:10]
    )
    username_candidates.extend(list(matched_usernames))

    tried = set()
    for uname in username_candidates:
        key = (uname or "").lower()
        if not key or key in tried:
            continue
        tried.add(key)
        user = authenticate(request, username=uname, password=password)
        if user:
            return user

    trimmed_password = password.strip()
    if trimmed_password != password:
        for uname in username_candidates:
            key = ((uname or "") + "|trimmed").lower()
            if not uname or key in tried:
                continue
            tried.add(key)
            user = authenticate(request, username=uname, password=trimmed_password)
            if user:
                return user
    return None


@require_http_methods(["GET", "POST"])
@never_cache
@ensure_csrf_cookie
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_redirect_url_for_user(request.user))

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        remember_me = request.POST.get("remember_me")

        if not username or not password:
            messages.error(request, "Username and password are required.")
            return render(request, "auth/login.html")

        user = _authenticate_flexible(request, username, password)
        if user is None:
            if not User.objects.filter(is_active=True).exists():
                messages.error(
                    request,
                    "No active accounts found on this server yet. Create one user (or set BOOTSTRAP_ADMIN_* env vars on Render).",
                )
            else:
                messages.error(request, "Invalid username/email/admission number or password.")
            return render(request, "auth/login.html")

        if not user.is_active:
            messages.error(request, "This account is inactive. Contact the administrator.")
            return render(request, "auth/login.html")
        if user.user_type == UserType.ADMIN and not user.is_superuser:
            messages.error(
                request,
                "Legacy Admin role is disabled. Assign one of: Admission, Staff, Finance, or Student.",
            )
            return render(request, "auth/login.html")

        login(request, user)
        try:
            AuditLog.objects.create(
                user=user,
                action="login",
                module="auth",
                path=request.path,
                method=request.method,
                status_code=200,
                metadata={"username": user.username},
            )
        except DatabaseError:
            # Never block login due to audit-log table/state issues.
            pass
        if remember_me:
            request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            request.session.set_expiry(0)

        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        # Role-based redirect (user_type stored as ADMIN, TRAINER, …)
        if user.is_superuser:
            if user.user_type != UserType.ADMIN:
                user.user_type = UserType.ADMIN
                user.save(update_fields=["user_type"])
            return redirect("admin_dashboard")

        ut = getattr(user, "user_type", None)
        if ut == UserType.ADMISSION:
            return redirect("admission_dashboard")
        if ut == UserType.ADMISSION_FINANCE:
            return redirect("admission_finance_dashboard")
        if ut == UserType.TRAINER:
            return redirect("trainer_dashboard")
        if ut == UserType.FINANCE:
            return redirect("finance_dashboard")
        if ut == UserType.STUDENT:
            return redirect("student_dashboard")
        if ut == UserType.PARENT:
            return redirect("parent_dashboard")
        return redirect("student_dashboard")

    return render(request, "auth/login.html")


def csrf_failure(request, reason="", template_name=None):
    messages.error(request, "Your session token expired. Please sign in again.")
    next_url = request.META.get("HTTP_REFERER") or reverse("login")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("login")
    return redirect(next_url)


@require_http_methods(["GET", "POST"])
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


@login_required
def dashboard_redirect(request):
    return redirect(_redirect_url_for_user(request.user))
