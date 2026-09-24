import logging
import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.matches.models import Match, MatchEvent, Participant, Room, RoomEvent
from config.observability import record_outbox_delivery_failure

logger = logging.getLogger("think_fast.outbox")


def match_group(match_id: object) -> str:
    return f"match.{match_id}"


def room_group(room_id: object) -> str:
    return f"room.{room_id}"


def _delivery_failed(event: MatchEvent | RoomEvent, exc: Exception) -> None:
    record_outbox_delivery_failure()
    event.publish_attempts += 1
    event.next_attempt_at = timezone.now() + timedelta(seconds=min(2**event.publish_attempts, 300))
    event.last_error = type(exc).__name__[:500]
    event.save(update_fields=["publish_attempts", "next_attempt_at", "last_error"])
    logger.warning(
        "outbox.delivery_failed",
        extra={
            "context": {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "attempt": event.publish_attempts,
            }
        },
    )


def publish_match_event(event_id: uuid.UUID) -> bool:
    event = MatchEvent.objects.get(pk=event_id)
    if event.published_at is not None:
        return True
    try:
        layer = get_channel_layer()
        if layer is None:
            raise RuntimeError("channel layer unavailable")
        async_to_sync(layer.group_send)(
            match_group(event.match_id), {"type": "match.event", "event_id": str(event.id)}
        )
    except Exception as exc:
        _delivery_failed(event, exc)
        return False
    event.published_at, event.last_error, event.next_attempt_at = timezone.now(), "", None
    event.save(update_fields=["published_at", "last_error", "next_attempt_at"])
    return True


def publish_room_event(event_id: uuid.UUID) -> bool:
    event = RoomEvent.objects.get(pk=event_id)
    if event.published_at is not None:
        return True
    try:
        layer = get_channel_layer()
        if layer is None:
            raise RuntimeError("channel layer unavailable")
        async_to_sync(layer.group_send)(
            room_group(event.room_id), {"type": "room.event", "event_id": str(event.id)}
        )
    except Exception as exc:
        _delivery_failed(event, exc)
        return False
    event.published_at, event.last_error, event.next_attempt_at = timezone.now(), "", None
    event.save(update_fields=["published_at", "last_error", "next_attempt_at"])
    return True


def _bump_match_sequence(match: Match) -> int:
    """Atomic increment without a second SELECT FOR UPDATE.

    Callers on the hot path (guess/commit) already hold the Match row via
    ``select_for_update`` in the outer transaction. A nested
    ``select_for_update`` + save only adds a savepoint and a second lock
    acquisition for the same row. An ``F()`` update is atomic at the DB level
    (no lost update when called without the outer lock) and the fresh value
    is read back so concurrent writers never reuse the same sequence.
    """
    Match.objects.filter(pk=match.pk).update(latest_sequence=F("latest_sequence") + 1)
    seq = Match.objects.filter(pk=match.pk).values_list("latest_sequence", flat=True).first()
    assert seq is not None
    match.latest_sequence = seq
    return seq


def _bump_room_sequence(room: Room) -> int:
    Room.objects.filter(pk=room.pk).update(latest_sequence=F("latest_sequence") + 1)
    seq = Room.objects.filter(pk=room.pk).values_list("latest_sequence", flat=True).first()
    assert seq is not None
    room.latest_sequence = seq
    return seq


def record_event(
    *,
    match: Match,
    event_type: str,
    visibility: str,
    payload: dict[str, object],
    participant: Participant | None = None,
) -> MatchEvent:
    def _create() -> MatchEvent:
        seq = _bump_match_sequence(match)
        event = MatchEvent.objects.create(
            match_id=match.pk,
            sequence=seq,
            event_type=event_type,
            visibility=visibility,
            participant=participant,
            payload=payload,
            occurred_at=timezone.now(),
        )
        transaction.on_commit(lambda: publish_match_event(event.id))
        return event

    # Avoid a savepoint per event when already inside the caller's transaction
    # (the common guess/commit path emits 1-2 events per write).
    if transaction.get_connection().in_atomic_block:
        return _create()
    with transaction.atomic():
        return _create()


def record_room_event(*, room: Room, event_type: str, payload: dict[str, object]) -> RoomEvent:
    def _create() -> RoomEvent:
        seq = _bump_room_sequence(room)
        event = RoomEvent.objects.create(
            room_id=room.pk,
            sequence=seq,
            event_type=event_type,
            payload=payload,
            occurred_at=timezone.now(),
        )
        transaction.on_commit(lambda: publish_room_event(event.id))
        return event

    if transaction.get_connection().in_atomic_block:
        return _create()
    with transaction.atomic():
        return _create()


def publish_pending(*, limit: int = 100) -> tuple[int, int]:
    now = timezone.now()
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    match_ids = list(
        MatchEvent.objects.filter(due, published_at__isnull=True).values_list("id", flat=True)[
            :limit
        ]
    )
    room_ids = list(
        RoomEvent.objects.filter(due, published_at__isnull=True).values_list("id", flat=True)[
            :limit
        ]
    )
    delivered = sum(publish_match_event(item) for item in match_ids)
    delivered += sum(publish_room_event(item) for item in room_ids)
    return delivered, len(match_ids) + len(room_ids)
