"""
Django settings for multicare_hms project.
Multicare Hospital Management System (HMS)
"""

import sys
from pathlib import Path

from decouple import Csv, config
from django.contrib.messages import constants as messages_constants

# ==========================================
# BASE DIRECTORY
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================================
# SECURITY
# ==========================================
SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv(),
)
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://multicare-hms.onrender.com",
    cast=Csv(),
)

# Production security hardening (only when DEBUG is False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# ==========================================
# APPLICATION DEFINITION
# ==========================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "crispy_forms",
    "crispy_bootstrap5",
    # Local apps
    "accounts",
    "core",
    "patients",
    "doctors",
    "appointments",
    "medical_records",
    "billing",
    "laboratory",
    "pharmacy",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]


_IS_TESTING = "test" in sys.argv or "pytest" in sys.modules

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if _IS_TESTING
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

ROOT_URLCONF = "multicare_hms.urls"

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

WSGI_APPLICATION = "multicare_hms.wsgi.application"


# ==========================================
# DATABASE - PostgreSQL
# ==========================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}


# ==========================================
# PASSWORD VALIDATION
# ==========================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ==========================================
# INTERNATIONALIZATION
# ==========================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ==========================================
# STATIC FILES (CSS, JavaScript, Images)
# ==========================================
STATIC_URL = "static/"

# Where our own static source files live (project-wide)
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Where collectstatic will gather everything for production
STATIC_ROOT = BASE_DIR / "staticfiles"


# ==========================================
# MEDIA FILES (User Uploads)
# ==========================================
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# ==========================================
# DEFAULTS
# ==========================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==========================================
# CUSTOM USER MODEL
# ==========================================
AUTH_USER_MODEL = "accounts.User"

# ==========================================
# AUTHENTICATION URLs
# ==========================================
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:profile"
LOGOUT_REDIRECT_URL = "core:home"

# ==========================================
# MESSAGES FRAMEWORK - Map Django tags to Bootstrap 5 classes
# ==========================================
MESSAGE_TAGS = {
    messages_constants.DEBUG: "secondary",
    messages_constants.INFO: "info",
    messages_constants.SUCCESS: "success",
    messages_constants.WARNING: "warning",
    messages_constants.ERROR: "danger",
}

# ==========================================
# CRISPY FORMS
# ==========================================
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# ==========================================
# DEV-ONLY: django-debug-toolbar
# ==========================================
if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
    INTERNAL_IPS = ["127.0.0.1"]


# ==========================================
# LOGGING
# ==========================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple" if DEBUG else "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            # DEBUG here logs every SQL query — very noisy. Only enable when hunting query perf.
            "level": "WARNING",
            "propagate": False,
        },
        "multicare_hms": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
# ---------- Email (Sprint 8 T-8.1) ----------
# Dev: prints reset emails to the console.
# Production: replace with SMTP settings below.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@multicare-hms.local"

# --- Production SMTP (uncomment + fill in) ---
# EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# EMAIL_HOST = "smtp.yourhost.com"
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = "user"
# EMAIL_HOST_PASSWORD = "pass"

# ---------- Cache (Sprint 8 T-8.10) ----------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "multicare-hms-default",
    },
}

# In production, swap for Redis:
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.redis.RedisCache",
#         "LOCATION": "redis://127.0.0.1:6379",
#     },
# }
