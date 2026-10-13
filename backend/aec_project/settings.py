"""
Django settings for the AEC Management System.

All business data lives in Apache CouchDB (see core/couchdb_client.py), so
Django's relational ORM is not used: no SQL database, no django.contrib.auth
models, no migrations. Users are CouchDB `user` documents and API requests are
authenticated with signed bearer tokens (authentication/tokens.py).

Secrets are read from the environment or the repository-root `.env` file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
REPO_ROOT = BASE_DIR.parent

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
    "core",
    "authentication",
    "students",
    "counsellors",
    "master_data",
    "frontend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aec_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

WSGI_APPLICATION = "aec_project.wsgi.application"

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

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["authentication.backends.CouchTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# A future standalone React frontend can be allowed here; the bundled
# frontend is served by Django itself on the same origin.
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Static files / i18n
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
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
