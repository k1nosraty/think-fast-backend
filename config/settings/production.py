"""Fail-closed production settings."""

from cryptography.fernet import Fernet

from config.settings.base import *  # noqa: F403
from config.settings.env import csv, fail, get

SECRET_KEY = get("DJANGO_SECRET_KEY", required=True)
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    fail("DJANGO_SECRET_KEY must be at least 50 characters and production-safe")

DEBUG = False
ALLOWED_HOSTS = csv("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    fail("DJANGO_ALLOWED_HOSTS must contain explicit hosts and may not contain '*'")

if not get("POSTGRES_PASSWORD"):
    fail("POSTGRES_PASSWORD is required in production")
if not get("REDIS_URL"):
    fail("REDIS_URL is required in production")
GAME_SECRET_ENCRYPTION_KEY = get("GAME_SECRET_ENCRYPTION_KEY", required=True)
try:
    Fernet(GAME_SECRET_ENCRYPTION_KEY.encode())
except (ValueError, TypeError):
    fail("GAME_SECRET_ENCRYPTION_KEY must be a URL-safe base64 Fernet key")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
