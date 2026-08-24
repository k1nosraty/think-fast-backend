import uuid

from django.db import transaction

from apps.analytics.models import AnalyticsEvent

ALLOWED_PROPERTIES = {
    "preset_id",
    "game_type",
    "match_mode",
    "schema_version",
    "evaluator_version",
    "outcome",
    "reason",
    "attempt_ordinal",
    "solved",
    "solve_duration_ms",
    "error_code",
    "state",
}
EVENT_TYPES = {
    "match_started",
    "match_completed",
    "attempt_accepted",
    "invalid_guess",
    "spam_blocked",
    "participant_abandoned",
    "participant_reconnected",
    "rematch_requested",
    "rematch_accepted",
    "rematch_declined",
    "rematch_expired",
}


def record_analytics(
    event_type: str,
    *,
    match_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
    **properties: object,
) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError("unsupported analytics event")
    forbidden = set(properties) - ALLOWED_PROPERTIES
    if forbidden:
        raise ValueError("unsafe analytics properties")
    transaction.on_commit(
        lambda: AnalyticsEvent.objects.create(
            event_type=event_type,
            match_id=match_id,
            room_id=room_id,
            properties=properties,
        ),
        robust=True,
    )
