"""Developer settings. Never import from a production process."""

import socket

from config.settings.base import *  # noqa: F403
from config.settings.base import BASE_DIR
from config.settings.env import boolean

SECRET_KEY = "local-only-insecure-key-not-for-production"
# Capacity measurement must run with DEBUG off: Django otherwise records every SQL
# query on the connection, which distorts latency and memory over a long load run.
# The T8 validation runner exports DJANGO_DEBUG=false for exactly this reason.
DEBUG = boolean("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
GAME_SECRET_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _is_service_reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# If PostgreSQL is not reachable, fall back to SQLite for effortless local development
if boolean("USE_SQLITE", False) or not _is_service_reachable("127.0.0.1", 5432):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# If Redis is not reachable, fall back to local-memory cache and in-memory channels
if boolean("USE_LOCMEM", False) or not _is_service_reachable("127.0.0.1", 6379):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "think-fast-local-cache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
