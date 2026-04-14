from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/login/", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("api/", include("apps.api.urls")),
    path("admin/", admin.site.urls),
    path("reports/", include("apps.reports.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
