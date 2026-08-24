"""Small environment parser; configuration errors fail early and clearly."""

import os
from typing import NoReturn

from django.core.exceptions import ImproperlyConfigured


def fail(message: str) -> NoReturn:
    raise ImproperlyConfigured(message)


def get(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        fail(f"Required environment variable {name} is not set")
    return value or ""


def csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in get(name, default).split(",") if item.strip()]


def integer(name: str, default: int) -> int:
    raw = get(name, str(default))
    try:
        return int(raw)
    except ValueError:
        fail(f"Environment variable {name} must be an integer")
