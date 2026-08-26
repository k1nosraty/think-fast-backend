import logging
from typing import Any

from django.conf import settings
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from config.logging import request_id_context
from config.observability import record_server_error

logger = logging.getLogger("think_fast.error")


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
        if settings.DEBUG:
            return None
        record_server_error()
        logger.error(
            "request.unhandled_exception",
            extra={
                "context": {
                    "view": type(context.get("view")).__name__,
                    "exception_type": type(exc).__name__,
                }
            },
        )
        return Response(
            {
                "code": "internal_error",
                "message": "An internal error occurred.",
                "field_errors": {},
                "request_id": request_id_context.get(),
                "retryable": True,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
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
