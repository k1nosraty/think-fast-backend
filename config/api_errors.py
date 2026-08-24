from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from config.logging import request_id_context


def _flatten(detail: Any) -> dict[str, list[str]]:
    if not isinstance(detail, dict):
        return {}
    return {
        str(field): [str(item) for item in (value if isinstance(value, list) else [value])]
        for field, value in detail.items()
    }


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    code = "invalid_request"
    retryable = False
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        code = "authentication_required"
    elif isinstance(exc, exceptions.PermissionDenied):
        code = "permission_denied"
    elif isinstance(exc, exceptions.Throttled):
        code, retryable = "rate_limited", True
    elif hasattr(exc, "default_code"):
        code = str(exc.default_code)
    payload: dict[str, Any] = {
        "code": code,
        "message": str(getattr(exc, "detail", "Request failed.")),
        "field_errors": _flatten(getattr(exc, "detail", {})),
        "request_id": request_id_context.get(),
        "retryable": retryable,
    }
    if isinstance(exc, exceptions.Throttled):
        payload["retry_after_seconds"] = int(getattr(exc, "wait", 0) or 0)
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
    response.data = payload
    return response
