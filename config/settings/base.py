"""Settings shared by every environment."""

from pathlib import Path

from config.settings.env import boolean, get, integer

BASE_DIR = Path(__file__).resolve().parents[2]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts.apps.AccountsConfig",
    "apps.games.apps.GamesConfig",
    "apps.matches.apps.MatchesConfig",
    "apps.realtime.apps.RealtimeConfig",
    "apps.analytics.apps.AnalyticsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Django's ASGI handler opens a ThreadSensitiveContext per request, and asgiref gives
# each such context its own single-worker executor. Every in-flight request therefore
# runs on its own thread and, with persistent connections, pins its own thread-local
# PostgreSQL connection. Connection count then tracks request concurrency with no upper
# bound, which exhausted the server's max_connections under the T8 Guess load profiles.
# A psycopg pool decouples the two: request threads wait briefly for a pooled connection
# instead of each opening one. Pooling and persistent connections are mutually exclusive
# in Django, so CONN_MAX_AGE must be 0 whenever the pool is enabled.
POSTGRES_POOL_ENABLED = boolean("POSTGRES_POOL_ENABLED", True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get("POSTGRES_DB", "think_fast"),
        "USER": get("POSTGRES_USER", "think_fast"),
        "PASSWORD": get("POSTGRES_PASSWORD", "think_fast_local"),
        "HOST": get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": integer("POSTGRES_PORT", 5432),
        "CONN_MAX_AGE": 0 if POSTGRES_POOL_ENABLED else integer("POSTGRES_CONN_MAX_AGE", 60),
        # Django forwards this to the pool as a pre-handout connection check, which
        # matters because the validation suite interrupts dependencies mid-run.
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": (
            {
                "pool": {
                    "min_size": integer("POSTGRES_POOL_MIN", 4),
                    "max_size": integer("POSTGRES_POOL_MAX", 32),
                    "timeout": integer("POSTGRES_POOL_TIMEOUT", 10),
                }
            }
            if POSTGRES_POOL_ENABLED
            else {}
        ),
    }
}

REDIS_URL = get("REDIS_URL", "redis://127.0.0.1:6379/0")
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": REDIS_URL,
                    "max_connections": integer("REDIS_CHANNEL_MAX_CONNECTIONS", 4096),
                    # redis-py 8 defaults to a five-second socket timeout, equal
                    # to channels_redis's blocking-pop interval. Leave enough
                    # margin for the response when the event loop is saturated.
                    "socket_timeout": integer("REDIS_CHANNEL_SOCKET_TIMEOUT", 15),
                    "socket_connect_timeout": integer("REDIS_CHANNEL_CONNECT_TIMEOUT", 10),
                }
            ]
        },
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.GuestAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_THROTTLE_CLASSES": ["apps.analytics.throttles.ResilientScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "guest_create": "20/hour",
        "game_read": "120/minute",
        "match_create": "30/hour",
        "guess": "120/minute",
        "snapshot": "120/minute",
        "leave": "30/hour",
        "rematch": "60/hour",
        "room_command": "120/minute",
        "challenge_commit": "30/hour",
    },
    "EXCEPTION_HANDLER": "config.api_errors.exception_handler",
}

GAME_SECRET_ENCRYPTION_KEY = get("GAME_SECRET_ENCRYPTION_KEY", "")
FRIENDLY_COUNTDOWN_SECONDS = integer("FRIENDLY_COUNTDOWN_SECONDS", 3)
PLAYER_CHALLENGE_SETUP_SECONDS = integer("PLAYER_CHALLENGE_SETUP_SECONDS", 120)
FRIENDLY_DISCONNECT_GRACE_SECONDS = integer("FRIENDLY_DISCONNECT_GRACE_SECONDS", 30)
REMATCH_REQUEST_TTL_SECONDS = integer("REMATCH_REQUEST_TTL_SECONDS", 60)
ENABLE_MATCH_CREATION = boolean("ENABLE_MATCH_CREATION", True)
ENABLE_PLAYER_AUTHORED_CHALLENGES = boolean("ENABLE_PLAYER_AUTHORED_CHALLENGES", True)
ENABLE_WEBSOCKETS = boolean("ENABLE_WEBSOCKETS", True)
LOAD_FIXTURES_ENABLED = boolean("LOAD_FIXTURES_ENABLED", False)
METRICS_BEARER_TOKEN = get("METRICS_BEARER_TOKEN", "")
SECRET_RETENTION_HOURS = integer("SECRET_RETENTION_HOURS", 24)
ATTEMPT_RETENTION_DAYS = integer("ATTEMPT_RETENTION_DAYS", 90)
MATCH_RETENTION_DAYS = integer("MATCH_RETENTION_DAYS", 365)
GUEST_RETENTION_DAYS = integer("GUEST_RETENTION_DAYS", 30)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "config.logging.RequestContextFilter"}},
    "formatters": {"json": {"()": "config.logging.StructuredJsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": get("LOG_LEVEL", "INFO")},
    "loggers": {"django.server": {"handlers": ["console"], "propagate": False}},
}
