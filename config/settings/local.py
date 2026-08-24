"""Developer settings. Never import from a production process."""

from config.settings.base import *  # noqa: F403

SECRET_KEY = "local-only-insecure-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
