"""Developer settings. Never import from a production process."""

from config.settings.base import *  # noqa: F403
from config.settings.env import boolean

SECRET_KEY = "local-only-insecure-key-not-for-production"
# Capacity measurement must run with DEBUG off: Django otherwise records every SQL
# query on the connection, which distorts latency and memory over a long load run.
# The T8 validation runner exports DJANGO_DEBUG=false for exactly this reason.
DEBUG = boolean("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
GAME_SECRET_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
