"""Request correlation without logging request bodies or credentials."""

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.logging import request_id_context
from config.observability import observe_request

logger = logging.getLogger("think_fast.request")


def _request_id(raw: str | None) -> str:
    if raw:
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            pass
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response.headers["X-Request-ID"] = request_id
            duration_seconds = time.monotonic() - started
            route = (
                str(request.resolver_match.route or "unmatched")
                if request.resolver_match
                else "unmatched"
            )
            observe_request(
                request.method or "UNKNOWN", route, response.status_code, duration_seconds
            )
            logger.info(
                "request.completed",
                extra={
                    "context": {
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_seconds * 1000, 2),
                    }
                },
            )
            return response
        finally:
            request_id_context.reset(token)
