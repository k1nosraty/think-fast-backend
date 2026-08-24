import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.matches.models import Match, Participant, Result
from apps.realtime.publisher import record_event


@transaction.atomic
def claim_connection(
    *, participant_id: uuid.UUID, connection_id: uuid.UUID, channel_name: str
) -> str:
    participant = (
        Participant.objects.select_for_update().select_related("match").get(pk=participant_id)
    )
    replaced_channel = participant.primary_channel_name if participant.connected else ""
    was_connected = participant.connected
    participant.connected = True
    participant.primary_connection_id = connection_id
    participant.primary_channel_name = channel_name
    participant.disconnected_at = None
    participant.grace_expires_at = None
    participant.save(
        update_fields=[
            "connected",
            "primary_connection_id",
            "primary_channel_name",
            "disconnected_at",
            "grace_expires_at",
        ]
    )
    if not was_connected:
        record_event(
            match=participant.match,
            event_type="participant.reconnected",
            visibility="match",
            participant=participant,
            payload={"participant_id": str(participant.id)},
        )
    return replaced_channel


@transaction.atomic
def release_connection(
    *, participant_id: uuid.UUID, connection_id: uuid.UUID, now: datetime | None = None
) -> float | None:
    now = now or timezone.now()
    participant = (
        Participant.objects.select_for_update().select_related("match").get(pk=participant_id)
    )
    if participant.primary_connection_id != connection_id:
        return None
    participant.connected = False
    participant.disconnected_at = now
    participant.grace_expires_at = now + timedelta(
        seconds=settings.FRIENDLY_DISCONNECT_GRACE_SECONDS
    )
    participant.primary_channel_name = ""
    participant.save(
        update_fields=["connected", "disconnected_at", "grace_expires_at", "primary_channel_name"]
    )
    record_event(
        match=participant.match,
        event_type="participant.disconnected",
        visibility="match",
        participant=participant,
        payload={
            "participant_id": str(participant.id),
            "grace_expires_at": participant.grace_expires_at.isoformat().replace("+00:00", "Z"),
        },
    )
    return float(settings.FRIENDLY_DISCONNECT_GRACE_SECONDS)


@transaction.atomic
def expire_disconnect_grace(
    *, participant_id: uuid.UUID, connection_id: uuid.UUID, now: datetime | None = None
) -> bool:
    now = now or timezone.now()
    participant = (
        Participant.objects.select_for_update().select_related("match").get(pk=participant_id)
    )
    if participant.connected or participant.primary_connection_id != connection_id:
        return False
    if participant.grace_expires_at is None or now < participant.grace_expires_at:
        return False
    match = Match.objects.select_for_update().get(pk=participant.match_id)
    if (
        match.state not in {Match.State.ACTIVE, Match.State.FINISHING}
        or participant.solve_state != Participant.SolveState.PLAYING
    ):
        return False
    participant.solve_state = Participant.SolveState.ABANDONED
    participant.save(update_fields=["solve_state"])
    match.state = Match.State.ABANDONED
    match.finished_at = now
    match.save(update_fields=["state", "finished_at"])
    other_ids = [
        str(item)
        for item in match.participants.exclude(pk=participant.pk).values_list("id", flat=True)
    ]
    Result.objects.create(
        match=match,
        outcome="abandoned",
        reason="abandoned",
        winner_participant_ids=other_ids,
        secret_revealed=False,
    )
    record_event(
        match=match,
        event_type="match.finished",
        visibility="match",
        payload={
            "outcome": "abandoned",
            "winner_participant_ids": other_ids,
            "reason": "abandoned",
            "secret_revealed": False,
        },
    )
    return True
