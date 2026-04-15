import os
from threading import Lock

from django.core.management import call_command
from django.db import connections
from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from apps.core.models import AuditLog


class RenderAutoMigrateMiddleware:
    """Run migrations once per worker on Render if DB isn't initialized."""

    _checked = False
    _lock = Lock()

    def __init__(self, get_response):
        self.get_response = get_response

    def _db_needs_migrate(self) -> bool:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1 FROM django_migrations LIMIT 1")
            return False
        except (DatabaseError, OperationalError, ProgrammingError):
            return True

    def __call__(self, request):
        if (os.getenv("RENDER") or "").lower() == "true" and not self.__class__._checked:
            with self.__class__._lock:
                if not self.__class__._checked:
                    if self._db_needs_migrate():
                        try:
                            call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
                        except Exception:
                            # Let request continue; downstream errors are safer than crash-loop at import.
                            pass
                    self.__class__._checked = True
        return self.get_response(request)


class AuditLogMiddleware:
    """Lightweight audit trail for mutating authenticated requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (
                request.user.is_authenticated
                and request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and request.path.startswith("/admin/")
            ):
                AuditLog.objects.create(
                    user=request.user,
                    action=f"{request.method} {request.path}",
                    module=request.path.strip("/").split("/")[0] if request.path.strip("/") else "",
                    path=request.path[:255],
                    method=request.method,
                    status_code=getattr(response, "status_code", 200),
                    ip_address=(request.META.get("REMOTE_ADDR") or "")[:64],
                    metadata={},
                )
        except Exception:
            # Never block user flow due to audit logging errors.
            pass
        return response
