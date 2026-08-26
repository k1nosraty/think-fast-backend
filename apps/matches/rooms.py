import secrets
import uuid
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.analytics.service import record_analytics
from apps.games.domain import rules_for_mode
from apps.games.registry import Rules, adapter_for
from apps.games.secrets import encrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import (
    Challenge,
    CommandRecord,
    Match,
    Participant,
    RematchProposal,
    Room,
    RoomMembership,
)
from apps.matches.services import fingerprint
from apps.realtime.publisher import record_event, record_room_event

JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def room_snapshot(room: Room) -> dict[str, object]:
    members = list(room.memberships.all())
    host_membership = next(member for member in members if member.guest_id == room.host_id)
    latest_match = room.matches.order_by("-created_at").first()
    proposal = (
        RematchProposal.objects.filter(Q(source_match=latest_match) | Q(new_match=latest_match))
        .order_by("-created_at")
        .first()
        if latest_match is not None
        else None
    )
    return {
        "room_id": str(room.id),
        "join_code": room.join_code,
        "host_participant_id": str(host_membership.id),
        "preset_id": room.preset_id,
        "state": room.state,
        "latest_sequence": room.latest_sequence,
        "latest_match_id": str(latest_match.id) if latest_match else None,
        "rematch": {
            "state": proposal.state,
            "requester_participant_id": str(
                next(member.id for member in members if member.guest_id == proposal.requester_id)
            ),
            "expires_at": proposal.expires_at.isoformat().replace("+00:00", "Z"),
            "new_match_id": str(proposal.new_match_id) if proposal.new_match_id else None,
        }
        if proposal
        else None,
        "members": [
            {
                "participant_id": str(member.id),
                "display_name": member.display_name,
                "avatar_id": member.avatar_id,
                "ready": member.ready,
                "connected": member.connected,
            }
            for member in members
        ],
    }


def _join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


def _create_friendly_match(
    *,
    room: Room,
    members: list[RoomMembership],
    secret_factory: Callable[[Rules], object] | None = None,
) -> Match:
    rules = rules_for_mode(room.preset_id, "friendly")
    assert rules is not None
    now = timezone.now()
    countdown_seconds = settings.FRIENDLY_COUNTDOWN_SECONDS
    started_at = now + timedelta(seconds=countdown_seconds)
    match = Match.objects.create(
        room=room,
        state=Match.State.ACTIVE if countdown_seconds == 0 else Match.State.COUNTDOWN,
        rules=rules.snapshot(),
        started_at=started_at,
        deadline=started_at + timedelta(seconds=rules.match_deadline_seconds),
    )
    for member in members:
        Participant.objects.create(
            match=match,
            guest=member.guest,
            display_name=member.display_name,
            avatar_id=member.avatar_id,
            connected=member.connected,
        )
    adapter = adapter_for(rules.game_type)
    secret = secret_factory(rules) if secret_factory else adapter.generate_secret(rules)
    Challenge.objects.create(
        match=match, protected_secret=encrypt_secret(adapter.encode_secret(rules, secret))
    )
    room.state = Room.State.ACTIVE
    room.save(update_fields=["state", "updated_at"])
    record_event(
        match=match,
        event_type="match.countdown_started",
        visibility="match",
        payload={"countdown_seconds": countdown_seconds},
    )
    if countdown_seconds == 0:
        record_event(
            match=match,
            event_type="match.started",
            visibility="match",
            payload={
                "started_at": started_at.isoformat().replace("+00:00", "Z"),
                "deadline": match.deadline.isoformat().replace("+00:00", "Z"),
            },
        )
    record_analytics(
        "match_started",
        match_id=match.id,
        room_id=room.id,
        preset_id=rules.preset_id,
        game_type=rules.game_type,
        match_mode=rules.match_mode,
        schema_version=rules.schema_version,
        evaluator_version=rules.evaluator_version,
    )
    return match


@transaction.atomic
def create_room(
    *, guest: GuestIdentity, command_id: uuid.UUID, preset_id: str
) -> tuple[Room, bool]:
    GuestIdentity.objects.select_for_update().get(pk=guest.pk)
    request_hash = fingerprint({"preset_id": preset_id})
    prior = (
        CommandRecord.objects.select_related("room")
        .filter(guest=guest, command_id=command_id)
        .first()
    )
    if prior:
        if (
            prior.operation != "create_room"
            or prior.request_fingerprint != request_hash
            or prior.room is None
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return prior.room, False
    if rules_for_mode(preset_id, "friendly") is None:
        raise GameAPIError("invalid_request", "Unknown preset_id.", status_code=400)
    for _ in range(10):
        code = _join_code()
        if not Room.objects.filter(join_code=code).exists():
            break
    else:
        raise GameAPIError("invalid_request", "Could not allocate a room code.", status_code=503)
    room = Room.objects.create(join_code=code, host=guest, preset_id=preset_id)
    RoomMembership.objects.create(
        room=room,
        guest=guest,
        display_name=guest.display_name,
        avatar_id=guest.avatar_id,
        connected=True,
    )
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="create_room",
        request_fingerprint=request_hash,
        room=room,
    )
    return room, True


@transaction.atomic
def join_room(
    *, guest: GuestIdentity, room_id: uuid.UUID, command_id: uuid.UUID
) -> tuple[Room, bool]:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    request_hash = fingerprint({"room_id": str(room_id)})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if (
            prior.operation != "join_room"
            or prior.request_fingerprint != request_hash
            or prior.room_id != room.id
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return room, False
    existing = RoomMembership.objects.filter(room=room, guest=guest).first()
    if existing:
        CommandRecord.objects.create(
            guest=guest,
            command_id=command_id,
            operation="join_room",
            request_fingerprint=request_hash,
            room=room,
        )
        return room, False
    if room.state not in {Room.State.WAITING, Room.State.READY_CHECK}:
        raise GameAPIError("room_full", "Room is no longer joinable.")
    if room.memberships.count() >= 2:
        raise GameAPIError("room_full", "Room already has two players.")
    RoomMembership.objects.filter(room=room).update(ready=False)
    joined_member = RoomMembership.objects.create(
        room=room,
        guest=guest,
        display_name=guest.display_name,
        avatar_id=guest.avatar_id,
        connected=True,
    )
    room.state = Room.State.READY_CHECK
    room.save(update_fields=["state", "updated_at"])
    record_room_event(
        room=room,
        event_type="room.player_joined",
        payload={
            "participant_id": str(joined_member.id),
            "display_name": joined_member.display_name,
            "avatar_id": joined_member.avatar_id,
        },
    )
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="join_room",
        request_fingerprint=request_hash,
        room=room,
    )
    return room, True


@transaction.atomic
def set_ready(
    *, guest: GuestIdentity, room_id: uuid.UUID, command_id: uuid.UUID, ready: bool
) -> Room:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    member = RoomMembership.objects.filter(room=room, guest=guest).first()
    if member is None:
        raise GameAPIError("permission_denied", "You are not a room member.", status_code=403)
    if room.state != Room.State.READY_CHECK:
        raise GameAPIError("not_ready", "Room is not accepting readiness changes.")
    request_hash = fingerprint({"ready": ready, "room_id": str(room_id)})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if prior.operation != "set_ready" or prior.request_fingerprint != request_hash:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return room
    member.ready = ready
    member.save(update_fields=["ready"])
    record_room_event(
        room=room,
        event_type="room.ready_changed",
        payload={"participant_id": str(member.id), "ready": ready},
    )
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="set_ready",
        request_fingerprint=request_hash,
        room=room,
    )
    return room


@transaction.atomic
def start_room(
    *,
    guest: GuestIdentity,
    room_id: uuid.UUID,
    command_id: uuid.UUID,
    secret_factory: Callable[[Rules], object] | None = None,
) -> tuple[Match, bool]:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    request_hash = fingerprint({"room_id": str(room_id)})
    prior = (
        CommandRecord.objects.select_related("match")
        .filter(guest=guest, command_id=command_id)
        .first()
    )
    if prior:
        if (
            prior.operation != "start_room"
            or prior.request_fingerprint != request_hash
            or prior.match is None
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return prior.match, False
    if room.host_id != guest.id:
        raise GameAPIError("not_room_host", "Only the room host can start.", status_code=403)
    members = list(room.memberships.select_for_update())
    if len(members) != 2 or not all(member.ready for member in members):
        raise GameAPIError("not_ready", "Exactly two ready players are required.")
    if room.state != Room.State.READY_CHECK:
        raise GameAPIError("not_ready", "Room cannot start in its current state.")
    match = _create_friendly_match(room=room, members=members, secret_factory=secret_factory)
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="start_room",
        request_fingerprint=request_hash,
        room=room,
        match=match,
    )
    return match, True


@transaction.atomic
def leave_room(*, guest: GuestIdentity, room_id: uuid.UUID, command_id: uuid.UUID) -> Room | None:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    request_hash = fingerprint({"room_id": str(room_id)})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if prior.operation != "leave_room" or prior.request_fingerprint != request_hash:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return None if room.state == Room.State.CLOSED else room
    if room.state == Room.State.ACTIVE:
        raise GameAPIError("match_not_active", "Leave the active Match instead.")
    member = RoomMembership.objects.filter(room=room, guest=guest).first()
    if member is None:
        raise GameAPIError("permission_denied", "You are not a room member.", status_code=403)
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="leave_room",
        request_fingerprint=request_hash,
        room=room,
    )
    record_room_event(
        room=room,
        event_type="room.player_left",
        payload={"participant_id": str(member.id)},
    )
    member.delete()
    remaining = RoomMembership.objects.filter(room=room).first()
    if remaining is None:
        room.state = Room.State.CLOSED
        room.save(update_fields=["state", "updated_at"])
        return None
    if room.host_id == guest.id:
        room.host = remaining.guest
    remaining.ready = False
    remaining.save(update_fields=["ready"])
    room.state = Room.State.WAITING
    room.save(update_fields=["host", "state", "updated_at"])
    return room
