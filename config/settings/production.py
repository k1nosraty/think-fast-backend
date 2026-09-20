"""Fail-closed production settings."""

from cryptography.fernet import Fernet

from config.settings.base import *  # noqa: F403
from config.settings.env import boolean, csv, fail, get

SECRET_KEY = get("DJANGO_SECRET_KEY", required=True)
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    fail("DJANGO_SECRET_KEY must be at least 50 characters and production-safe")

DEBUG = False
ALLOWED_HOSTS = csv("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    fail("DJANGO_ALLOWED_HOSTS must contain explicit hosts and may not contain '*'")

CSRF_TRUSTED_ORIGINS = csv("DJANGO_CSRF_TRUSTED_ORIGINS")
if any("*" in origin for origin in CSRF_TRUSTED_ORIGINS):
    fail("DJANGO_CSRF_TRUSTED_ORIGINS may not contain wildcards")

if not get("POSTGRES_PASSWORD"):
    fail("POSTGRES_PASSWORD is required in production")
if not get("REDIS_URL"):
    fail("REDIS_URL is required in production")
GAME_SECRET_ENCRYPTION_KEY = get("GAME_SECRET_ENCRYPTION_KEY", required=True)
try:
    Fernet(GAME_SECRET_ENCRYPTION_KEY.encode())
except (ValueError, TypeError):
    fail("GAME_SECRET_ENCRYPTION_KEY must be a URL-safe base64 Fernet key")
METRICS_BEARER_TOKEN = get("METRICS_BEARER_TOKEN", required=True)
if len(METRICS_BEARER_TOKEN) < 32:
    fail("METRICS_BEARER_TOKEN must contain at least 32 characters")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
if boolean("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
