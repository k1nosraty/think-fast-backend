from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client


@pytest.mark.django_db
def test_liveness_is_dependency_free(client: Client) -> None:
    response = client.get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_reports_database_and_cache(client: Client) -> None:
    response = client.get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


@pytest.mark.django_db
def test_readiness_fails_closed_when_cache_is_unavailable(client: Client) -> None:
    with patch.object(cache, "set", side_effect=ConnectionError):
        response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json()["checks"]["cache"] == "error"
