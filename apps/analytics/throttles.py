import uuid
from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import ScopedRateThrottle

from apps.analytics.service import record_analytics
from apps.matches.models import Match


class AnalyticsScopedRateThrottle(ScopedRateThrottle):
    """Record only aggregate metadata when the Guess rate limit blocks a request."""

    def allow_request(self, request: Request, view: Any) -> bool:
        allowed = super().allow_request(request, view)
        if allowed or getattr(view, "throttle_scope", None) != "guess":
            return allowed
        match_id = getattr(view, "kwargs", {}).get("match_id")
        if not isinstance(match_id, (uuid.UUID, str)):
            return False
        match = Match.objects.filter(pk=match_id).first()
        if match is not None:
            record_analytics(
                "spam_blocked",
                match_id=match.id,
                room_id=match.room_id,
                preset_id=str(match.rules["preset_id"]),
                reason="rate_limit",
            )
        return False
