"""
Django settings for the AEC Management System.

All business data lives in Apache CouchDB (see apps/core/couchdb_client.py), so
Django's relational ORM is not used: no SQL database, no django.contrib.auth
models, no migrations. Users are CouchDB `user` documents and API requests are
authenticated with signed bearer tokens (apps/accounts/tokens.py).

The web client is a React app in the repository-level `frontend/` folder. Its
production build (frontend/dist) is served from here, so the API and UI share one origin.

Secrets are read from the environment or the repository-root `.env` file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
REPO_ROOT = BASE_DIR.parent
FRONTEND_DIR = REPO_ROOT / "frontend"  # React app; `npm run build` writes frontend/dist

load_dotenv(REPO_ROOT / ".env")
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
    # Development-only fallback. Set DJANGO_SECRET_KEY in .env for anything shared.
    SECRET_KEY = "dev-insecure-aec-secret-key-change-me"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    # Domain apps (backend/apps/)
    "apps.core",
    "apps.accounts",
    "apps.students",
    "apps.counsellors",
    "apps.universities",
    "apps.dashboard",
    "apps.applications",
    "apps.documents",
    "apps.counselling",
    "apps.recommendations",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# No relational database - CouchDB is the only data store.
DATABASES = {}

# ---------------------------------------------------------------------------
# CouchDB
# ---------------------------------------------------------------------------
COUCHDB_URL = os.getenv("COUCHDB_URL", "http://127.0.0.1:5984/")
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASSWORD = os.getenv("COUCHDB_PASSWORD", "")
COUCHDB_NAME = os.getenv("COUCHDB_NAME", "counselling_db")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_TOKEN_MAX_AGE = int(os.getenv("AUTH_TOKEN_MAX_AGE", str(8 * 60 * 60)))  # seconds
AUTH_MIN_PASSWORD_LENGTH = 8

# Forgot-password codes (apps/accounts/password_reset.py)
PASSWORD_RESET_CODE_TTL = int(os.getenv("PASSWORD_RESET_CODE_TTL", "600"))  # seconds a code stays valid
PASSWORD_RESET_COOLDOWN = int(os.getenv("PASSWORD_RESET_COOLDOWN", "60"))   # seconds before another code can be sent
PASSWORD_RESET_MAX_ATTEMPTS = 5

# Outgoing email (Django 6.1 MAILERS). With no EMAIL_HOST the codes are printed in the server
# console (development); set EMAIL_HOST (+ user/password) in .env to send real email.
_SMTP_HOST = os.getenv("EMAIL_HOST", "")
_SMTP_USER = os.getenv("EMAIL_HOST_USER", "")
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend" if _SMTP_HOST else "django.core.mail.backends.console.EmailBackend",
        **({"OPTIONS": {
            "host": _SMTP_HOST,
            "port": int(os.getenv("EMAIL_PORT", "587")),
            "username": _SMTP_USER,
            "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
            "use_tls": os.getenv("EMAIL_USE_TLS", "true").lower() == "true",
            "timeout": 15,
        }} if _SMTP_HOST else {}),
    },
}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or _SMTP_USER or "AEC Admissions <no-reply@aec.local>"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.backends.CouchTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Recommendation engine factor weights (apps/recommendations/engine.py); any subset overrides the defaults.
RECOMMENDATION_WEIGHTS = {"country": 30, "course": 30, "academic": 20, "intake": 10, "budget": 10}

# Not needed for the React app: Django serves its build, and the Vite dev server
# proxies /api, so both run on one origin. Only list origins hosted elsewhere.
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Static files / i18n
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
# Vite builds into frontend/dist with base "/static/" and content-hashed asset names,
# so a changed file always gets a new URL and browsers never run stale code.
# Only the assets and public files are exposed under /static/, never dist/index.html: the app's
# pages live at their own URLs (/login/, /dashboard/, ...), so /static/index.html must not load it.
STATICFILES_DIRS = [("assets", d) for d in [FRONTEND_DIR / "dist" / "assets"] if d.is_dir()] + [FRONTEND_DIR / "public"]
STATIC_ROOT = BASE_DIR / "staticfiles"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 3600
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        "aec": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "WARNING"},
    },
}
