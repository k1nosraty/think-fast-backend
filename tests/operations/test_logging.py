import json
import logging
import uuid

from django.test import Client

from config.logging import StructuredJsonFormatter, redact


def test_request_id_is_preserved_when_valid(client: Client) -> None:
    request_id = str(uuid.uuid4())
    response = client.get("/health/live/", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_is_replaced(client: Client) -> None:
    response = client.get("/health/live/", headers={"X-Request-ID": "attacker-controlled"})
    assert str(uuid.UUID(response.headers["X-Request-ID"])) == response.headers["X-Request-ID"]


def test_structured_formatter_redacts_sensitive_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "safe", (), None)
    record.request_id = "request-1"
    record.context = {"guess": "436781", "nested": {"token": "abc"}, "status": "ok"}
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert payload["context"] == {
        "guess": "[REDACTED]",
        "nested": {"token": "[REDACTED]"},
        "status": "ok",
    }
    assert "436781" not in json.dumps(payload)


def test_redaction_handles_lists() -> None:
    assert redact([{"password": "unsafe"}]) == [{"password": "[REDACTED]"}]
