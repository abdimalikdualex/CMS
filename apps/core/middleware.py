from apps.core.models import AuditLog


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
