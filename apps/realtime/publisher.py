from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.matches.models import Match, MatchEvent, Participant, Room, RoomEvent


def match_group(match_id: object) -> str:
    return f"match.{match_id}"


def room_group(room_id: object) -> str:
    return f"room.{room_id}"


def record_event(
    *,
    match: Match,
    event_type: str,
    visibility: str,
    payload: dict[str, object],
    participant: Participant | None = None,
) -> MatchEvent:
    match.latest_sequence += 1
    match.save(update_fields=["latest_sequence"])
    event = MatchEvent.objects.create(
        match=match,
        sequence=match.latest_sequence,
        event_type=event_type,
        visibility=visibility,
        participant=participant,
        payload=payload,
        occurred_at=timezone.now(),
    )

    def publish() -> None:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                match_group(match.id), {"type": "match.event", "event_id": str(event.id)}
            )

    transaction.on_commit(publish)
    return event


def record_room_event(*, room: Room, event_type: str, payload: dict[str, object]) -> RoomEvent:
    room.latest_sequence += 1
    room.save(update_fields=["latest_sequence"])
    event = RoomEvent.objects.create(
        room=room,
        sequence=room.latest_sequence,
        event_type=event_type,
        payload=payload,
        occurred_at=timezone.now(),
    )

    def publish() -> None:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                room_group(room.id), {"type": "room.event", "event_id": str(event.id)}
            )

    transaction.on_commit(publish)
    return event
