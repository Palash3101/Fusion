"""
Test-only settings for PS1 module tests.
Inherits from development, but uses SQLite in-memory DB
so no PostgreSQL migration conflicts occur.
"""
from Fusion.settings.common import *  # noqa

DEBUG = True
SECRET_KEY = "test-secret-key-ps1"

ALLOWED_HOSTS = ["*"]

# Use SQLite in-memory — bypasses the broken programme_curriculum migration
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

# Disable debug toolbar (PostgreSQL-only feature)
INSTALLED_APPS = [a for a in INSTALLED_APPS if a not in (
    "debug_toolbar", "django_extensions",
)]
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]

# Silence logging during tests
LOGGING = {}

# Speed up password hashing in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
