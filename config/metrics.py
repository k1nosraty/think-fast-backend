import hmac
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from apps.analytics.models import AnalyticsEvent
from apps.matches.models import Match, MatchEvent, RoomEvent
from config.observability import render_process_metrics

_STARTED_AT = time.monotonic()


@require_GET
def metrics(request: HttpRequest) -> HttpResponse:
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.METRICS_BEARER_TOKEN}"
    if not settings.METRICS_BEARER_TOKEN or not hmac.compare_digest(authorization, expected):
        return HttpResponse(status=404)
    try:
        values = {
            "think_fast_process_uptime_seconds": max(0.0, time.monotonic() - _STARTED_AT),
            "think_fast_matches_active": Match.objects.filter(
                state__in=[Match.State.SETUP, Match.State.COUNTDOWN, Match.State.ACTIVE]
            ).count(),
            "think_fast_match_outbox_pending": MatchEvent.objects.filter(
                published_at__isnull=True
            ).count(),
            "think_fast_room_outbox_pending": RoomEvent.objects.filter(
                published_at__isnull=True
            ).count(),
            "think_fast_analytics_events_total": AnalyticsEvent.objects.count(),
        }
    except Exception:
        return HttpResponse(
            "# metrics backend unavailable\n", status=503, content_type="text/plain"
        )
    lines = [*(f"{name} {value}" for name, value in values.items()), *render_process_metrics()]
    body = "\n".join(lines) + "\n"
    return HttpResponse(body, content_type="text/plain; version=0.0.4")
