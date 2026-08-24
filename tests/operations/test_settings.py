import os
import subprocess
import sys

from django.apps import apps


def test_expected_boundaries_are_registered_without_domain_models() -> None:
    for label in ("accounts", "games", "matches", "realtime"):
        config = apps.get_app_config(label)
        assert list(config.get_models()) == []


def test_production_settings_refuse_missing_secrets() -> None:
    environment = os.environ.copy()
    for name in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "POSTGRES_PASSWORD", "REDIS_URL"):
        environment.pop(name, None)
    completed = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "DJANGO_SECRET_KEY" in completed.stderr


def test_production_settings_accept_secure_explicit_configuration() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SECRET_KEY": "x" * 64,
            "DJANGO_ALLOWED_HOSTS": "api.example.test",
            "POSTGRES_PASSWORD": "not-a-real-secret",
            "REDIS_URL": "redis://redis:6379/0",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
