import threading
from collections import Counter

_lock = threading.Lock()
_requests: Counter[tuple[str, str, int]] = Counter()
_request_duration_sum = 0.0
_request_duration_count = 0
_server_errors = 0
_websockets_active = 0
_outbox_delivery_failures = 0


def observe_request(method: str, route: str, status_code: int, duration_seconds: float) -> None:
    global _request_duration_count, _request_duration_sum
    with _lock:
        _requests[(method, route, status_code)] += 1
        _request_duration_count += 1
        _request_duration_sum += duration_seconds


def record_server_error() -> None:
    global _server_errors
    with _lock:
        _server_errors += 1


def websocket_connected() -> None:
    global _websockets_active
    with _lock:
        _websockets_active += 1


def websocket_disconnected() -> None:
    global _websockets_active
    with _lock:
        _websockets_active = max(0, _websockets_active - 1)


def record_outbox_delivery_failure() -> None:
    global _outbox_delivery_failures
    with _lock:
        _outbox_delivery_failures += 1


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_process_metrics() -> list[str]:
    with _lock:
        lines = [
            f"think_fast_request_duration_seconds_sum {_request_duration_sum}",
            f"think_fast_request_duration_seconds_count {_request_duration_count}",
            f"think_fast_server_errors_total {_server_errors}",
            f"think_fast_websockets_active {_websockets_active}",
            f"think_fast_outbox_delivery_failures_total {_outbox_delivery_failures}",
        ]
        lines.extend(
            "think_fast_http_requests_total"
            f'{{method="{_escape(method)}",route="{_escape(route)}",status="{status}"}} {count}'
            for (method, route, status), count in sorted(_requests.items())
        )
        return lines
