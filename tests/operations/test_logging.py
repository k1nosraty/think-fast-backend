import json
import logging
import uuid

from _pytest.logging import LogCaptureFixture
from django.test import Client, override_settings

from config.api_errors import exception_handler
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


@override_settings(DEBUG=False)
def test_unhandled_exception_is_safe_for_response_and_logs(caplog: LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="think_fast.error"):
        response = exception_handler(ValueError("secret=12345"), {"view": object()})
    assert response is not None
    assert response.status_code == 500
    assert response.data["code"] == "internal_error"
    assert "12345" not in str(response.data)
    assert "12345" not in caplog.text
