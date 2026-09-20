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
from apps.matches.features import require_match_creation, require_player_authored_challenges
from apps.matches.models import (
    Challenge,
    CommandRecord,
    Match,
    Participant,
    RematchProposal,
    Room,
    RoomMembership,
)
from apps.matches.services import check_command_prior, fingerprint
from apps.realtime.publisher import record_event, record_room_event

JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def room_snapshot(room: Room, guest: GuestIdentity | None = None) -> dict[str, object]:
    rules = rules_for_mode(room.preset_id, "friendly")
    if rules is None:
        raise GameAPIError("invalid_request", "Room rules are not available.", status_code=500)
    members = list(room.memberships.all())
    # Defensive: host membership may be missing; fallback to first member if available
    host_membership = next(
        (member for member in members if member.guest_id == room.host_id), None
    )
    if host_membership is None and members:
        host_membership = members[0]
    viewer_membership = (
        next((member for member in members if member.guest_id == guest.id), None)
        if guest is not None
        else None
    )
    latest_match = room.matches.order_by("-created_at").first()
    proposal = (
        RematchProposal.objects.filter(Q(source_match=latest_match) | Q(new_match=latest_match))
        .order_by("-created_at")
        .first()
        if latest_match is not None
        else None
    )
    rematch_payload = None
    if proposal is not None:
        requester_member = next(
            (member for member in members if member.guest_id == proposal.requester_id), None
        )
        rematch_payload = {
            "state": proposal.state,
            "requester_participant_id": str(requester_member.id)
            if requester_member
            else None,
            "expires_at": proposal.expires_at.isoformat().replace("+00:00", "Z"),
            "new_match_id": str(proposal.new_match_id) if proposal.new_match_id else None,
        }
    return {
        "room_id": str(room.id),
        "join_code": room.join_code,
        "host_participant_id": str(host_membership.id) if host_membership else None,
        "viewer_participant_id": str(viewer_membership.id) if viewer_membership else None,
        "preset_id": room.preset_id,
        "rules": rules.snapshot(),
        "challenge_source": room.challenge_source,
        "room_mode": room.room_mode,
        "rounds_count": room.rounds_count,
        "state": room.state,
        "latest_sequence": room.latest_sequence,
        "latest_match_id": str(latest_match.id) if latest_match else None,
        "rematch": rematch_payload,
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
    player_authored = room.challenge_source == Room.ChallengeSource.PLAYERS
    started_at = now + timedelta(seconds=countdown_seconds)
    is_party = room.room_mode == "party"
    match = Match.objects.create(
        room=room,
        state=Match.State.SETUP
        if player_authored
        else (Match.State.ACTIVE if countdown_seconds == 0 else Match.State.COUNTDOWN),
        round_state="creator_setup"
        if player_authored
        else ("active" if countdown_seconds == 0 else "countdown"),
        round_number=1,
        total_rounds=room.rounds_count if is_party else 1,
        rules=rules.snapshot(),
        started_at=started_at,
        deadline=started_at + timedelta(seconds=rules.match_deadline_seconds),
        setup_expires_at=now + timedelta(seconds=settings.PLAYER_CHALLENGE_SETUP_SECONDS)
        if player_authored
        else None,
    )
    participants: list[Participant] = []
    for member in members:
        p = Participant.objects.create(
            match=match,
            guest=member.guest,
            display_name=member.display_name,
            avatar_id=member.avatar_id,
            connected=member.connected,
        )
        participants.append(p)
    if player_authored and is_party:
        host_p = next((p for p in participants if p.guest_id == room.host_id), participants[0])
        host_p.is_creator = True
        host_p.save(update_fields=["is_creator"])
        match.creator = host_p
        match.save(update_fields=["creator"])
    elif not player_authored:
        adapter = adapter_for(rules.game_type)
        secret = secret_factory(rules) if secret_factory else adapter.generate_secret(rules)
        Challenge.objects.create(
            match=match,
            round_number=1,
            protected_secret=encrypt_secret(adapter.encode_secret(rules, secret)),
        )
    room.state = Room.State.ACTIVE
    room.save(update_fields=["state", "updated_at"])
    if player_authored and is_party:
        assert match.setup_expires_at is not None
        record_event(
            match=match,
            event_type="creator.selected",
            visibility="match",
            payload={
                "creator_participant_id": str(host_p.id),
                "creator_display_name": host_p.display_name,
                "round_number": 1,
            },
        )
        record_event(
            match=match,
            event_type="round.created",
            visibility="match",
            payload={
                "round_number": 1,
                "total_rounds": match.total_rounds,
                "creator_participant_id": str(host_p.id),
                "creator_display_name": host_p.display_name,
                "expires_at": match.setup_expires_at.isoformat().replace("+00:00", "Z"),
            },
        )
        record_event(
            match=match,
            event_type="challenge.setup_started",
            visibility="match",
            payload={
                "expires_at": match.setup_expires_at.isoformat().replace("+00:00", "Z"),
                "creator_participant_id": str(host_p.id),
                "required_count": 1,
            },
        )
    elif player_authored:
        assert match.setup_expires_at is not None
        record_event(
            match=match,
            event_type="challenge.setup_started",
            visibility="match",
            payload={
                "expires_at": match.setup_expires_at.isoformat().replace("+00:00", "Z"),
                "required_count": 2,
            },
        )
    else:
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
    *,
    guest: GuestIdentity,
    command_id: uuid.UUID,
    preset_id: str,
    challenge_source: str = Room.ChallengeSource.SYSTEM,
    room_mode: str = "duel",
    rounds_count: int = 5,
) -> tuple[Room, bool]:
    require_match_creation()
    if challenge_source == Room.ChallengeSource.PLAYERS:
        require_player_authored_challenges()
    GuestIdentity.objects.select_for_update().get(pk=guest.pk)
    request_hash = fingerprint(
        {
            "preset_id": preset_id,
            "challenge_source": challenge_source,
            "room_mode": room_mode,
            "rounds_count": rounds_count,
        }
    )
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="create_room", request_hash=request_hash
    )
    if prior is not None:
        if prior.room is None:
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
    room = Room.objects.create(
        join_code=code,
        host=guest,
        preset_id=preset_id,
        challenge_source=challenge_source,
        room_mode=room_mode,
        rounds_count=rounds_count,
    )
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
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="join_room", request_hash=request_hash
    )
    if prior is not None:
        if prior.room_id != room.id:
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
    max_players = 2 if room.room_mode == "duel" else 8
    if room.memberships.count() >= max_players:
        raise GameAPIError(
            "room_full", f"Room has reached its maximum capacity of {max_players} players."
        )
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
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="set_ready", request_hash=request_hash
    )
    if prior is not None:
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
    require_match_creation()
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    request_hash = fingerprint({"room_id": str(room_id)})
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="start_room", request_hash=request_hash
    )
    if prior is not None:
        if prior.match is None:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return prior.match, False
    if room.host_id != guest.id:
        raise GameAPIError("not_room_host", "Only the room host can start.", status_code=403)
    members = list(room.memberships.select_for_update())
    minimum_players = 2 if room.room_mode == "duel" else 3
    if len(members) < minimum_players or not all(member.ready for member in members):
        raise GameAPIError("not_ready", f"At least {minimum_players} ready players are required.")
    if room.room_mode == "duel" and len(members) != 2:
        raise GameAPIError("not_ready", "Exactly two ready players are required for Duel mode.")
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
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="leave_room", request_hash=request_hash
    )
    if prior is not None:
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
    remaining_members = list(RoomMembership.objects.filter(room=room).select_for_update())
    if not remaining_members:
        room.state = Room.State.CLOSED
        room.save(update_fields=["state", "updated_at"])
        return None
    if room.host_id == guest.id:
        room.host = remaining_members[0].guest
    # Reset readiness for all remaining members to avoid stale readiness
    RoomMembership.objects.filter(room=room).update(ready=False)
    remaining_count = len(remaining_members)
    # Derive state from actual Party minimum: duel needs 2, party needs 3
    minimum_players = 2 if room.room_mode == "duel" else 3
    room.state = (
        Room.State.READY_CHECK if remaining_count >= minimum_players else Room.State.WAITING
    )
    # For consistency, also READY_CHECK when 2 members remain even if party minimum is 3,
    # but we use minimum for WAITING vs READY_CHECK to satisfy task requirement.
    # The above logic already handles party minimum.
    room.save(update_fields=["host", "state", "updated_at"])
    return room


def room_for_join_code(join_code: str) -> Room | None:
    return Room.objects.filter(join_code=join_code.upper()).exclude(state=Room.State.CLOSED).first()


@transaction.atomic
def kick_member(
    *,
    guest: GuestIdentity,
    room_id: uuid.UUID,
    target_participant_id: uuid.UUID,
    command_id: uuid.UUID,
) -> Room:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    if room.host_id != guest.id:
        raise GameAPIError("not_room_host", "Only the room host can kick.", status_code=403)
    if room.state not in {Room.State.WAITING, Room.State.READY_CHECK}:
        raise GameAPIError("not_ready", "Room cannot be changed in its current state.")
    request_hash = fingerprint(
        {"room_id": str(room_id), "target_participant_id": str(target_participant_id)}
    )
    prior = check_command_prior(
        guest=guest, command_id=command_id, operation="kick_member", request_hash=request_hash
    )
    if prior is not None:
        # Idempotent replay: do not repeat mutation
        return room
    target = RoomMembership.objects.filter(room=room, id=target_participant_id).first()
    if target is None:
        raise GameAPIError("member_not_found", "Member was not found.", status_code=404)
    if target.guest_id == room.host_id:
        raise GameAPIError("invalid_request", "The host cannot be kicked.", status_code=400)
    host_member = RoomMembership.objects.filter(room=room, guest=guest).first()
    if host_member is None:
        raise GameAPIError("permission_denied", "You are not a room member.", status_code=403)
    if target.id == host_member.id:
        raise GameAPIError("invalid_request", "You cannot kick yourself.", status_code=400)
    # Record before deletion
    record_room_event(
        room=room,
        event_type="room.player_left",
        payload={"participant_id": str(target.id)},
    )
    target.delete()
    # Reset readiness for all remaining members, not just one
    RoomMembership.objects.filter(room=room).update(ready=False)
    remaining_count = RoomMembership.objects.filter(room=room).count()
    # Derive state from actual Party minimum instead of blindly WAITING
    if room.room_mode == "duel":
        minimum_players = 2
    else:
        minimum_players = 3
    if remaining_count == 0:
        room.state = Room.State.CLOSED
    elif remaining_count >= minimum_players:
        room.state = Room.State.READY_CHECK
    else:
        room.state = Room.State.WAITING
    room.save(update_fields=["state", "updated_at"])
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="kick_member",
        request_fingerprint=request_hash,
        room=room,
    )
    return room


@transaction.atomic
def update_room_rules(*, guest: GuestIdentity, room_id: uuid.UUID, preset_id: str) -> Room:
    room = Room.objects.select_for_update().filter(pk=room_id).first()
    if room is None:
        raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
    if room.host_id != guest.id:
        raise GameAPIError("not_room_host", "Only the room host can change rules.", status_code=403)
    if room.state not in {Room.State.WAITING, Room.State.READY_CHECK}:
        raise GameAPIError("not_ready", "Rules can only change before the match starts.")
    if rules_for_mode(preset_id, "friendly") is None:
        raise GameAPIError("invalid_request", "Unknown preset_id.", status_code=400)
    room.preset_id = preset_id
    RoomMembership.objects.filter(room=room).update(ready=False)
    room.state = (
        Room.State.READY_CHECK
        if RoomMembership.objects.filter(room=room).count() >= 2
        else Room.State.WAITING
    )
    room.save(update_fields=["preset_id", "state", "updated_at"])
    record_room_event(
        room=room,
        event_type="room.rules_changed",
        payload={"preset_id": preset_id},
    )
    return room
