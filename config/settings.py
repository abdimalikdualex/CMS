import os
from pathlib import Path

from django.urls import reverse_lazy
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# SECURITY
# =========================

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-change-in-production-not-for-production"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    ".onrender.com,127.0.0.1,localhost"
).split(",")

# =========================
# APPS
# =========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework.authtoken",

    "apps.core",
    "apps.api",
    "apps.accounts",
    "apps.students",
    "apps.academics",
    "apps.assessments",
    "apps.finance",
    "apps.library",
    "apps.attachments",
    "apps.timetable",
    "apps.communications",
    "apps.reports",
]

# =========================
# MIDDLEWARE
# =========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    # ✅ REQUIRED FOR RENDER STATIC FILES
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "apps.accounts.middleware.RoleContextMiddleware",
    "apps.core.middleware.AuditLogMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# =========================
# TEMPLATES
# =========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# =========================
# DATABASE
# =========================

def _use_postgresql() -> bool:
    if os.environ.get("FORCE_SQLITE", "").lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("USE_SQLITE", "").lower() in ("1", "true", "yes"):
        return False
    return os.environ.get("USE_POSTGRES", "").lower() in ("1", "true", "yes")


if not _use_postgresql():
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "tvet_cms"),
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "OPTIONS": {
                "connect_timeout": int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "10")),
            },
        }
    }

# =========================
# AUTH
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

# =========================
# INTERNATIONALIZATION
# =========================

LANGUAGE_CODE = "en-ke"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# =========================
# STATIC FILES (RENDER FIX)
# =========================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ✅ WhiteNoise production storage
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# DEFAULT AUTO FIELD
# =========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =========================
# REST FRAMEWORK
# =========================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# =========================
# AUTH REDIRECTS
# =========================

LOGIN_URL = reverse_lazy("login")
LOGIN_REDIRECT_URL = reverse_lazy("dashboard")
LOGOUT_REDIRECT_URL = reverse_lazy("login")

CSRF_FAILURE_VIEW = "apps.accounts.views.csrf_failure"

# =========================
# SECURITY (PRODUCTION ONLY)
# =========================

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"