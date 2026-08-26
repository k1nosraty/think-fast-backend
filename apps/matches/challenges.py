import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.games.color import ColorValidationError
from apps.games.domain import GuessValidationError
from apps.games.registry import adapter_for, rules_from_snapshot
from apps.games.secrets import encrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import Challenge, CommandRecord, Match, Participant, Room, RoomMembership
from apps.matches.services import fingerprint
from apps.realtime.publisher import record_event


def _cancel_setup_locked(match: Match, *, now: datetime, reason: str) -> bool:
    if match.state != Match.State.SETUP:
        return False
    match.state = Match.State.CANCELLED
    match.finished_at = now
    match.save(update_fields=["state", "finished_at"])
    if match.room_id:
        room = Room.objects.select_for_update().get(pk=match.room_id)
        room.state = Room.State.READY_CHECK
        room.save(update_fields=["state", "updated_at"])
        RoomMembership.objects.filter(room=room).update(ready=False)
    record_event(
        match=match,
        event_type="challenge.setup_cancelled",
        visibility="match",
        payload={"reason": reason},
    )
    return True


@transaction.atomic
def expire_challenge_setup(match_id: uuid.UUID, *, now: datetime | None = None) -> bool:
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        return False
    current = now or timezone.now()
    if match.setup_expires_at is None or current < match.setup_expires_at:
        return False
    return _cancel_setup_locked(match, now=current, reason="setup_timeout")


@transaction.atomic
def _commit_challenge(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    secret: object,
    now: datetime | None = None,
) -> tuple[Match, bool, bool]:
    current = now or timezone.now()
    match = Match.objects.select_for_update().select_related("room").filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)
    creator = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if creator is None:
        raise GameAPIError("permission_denied", "You are not a participant.", status_code=403)
    request_hash = fingerprint({"match_id": str(match_id), "secret": secret})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if (
            prior.operation != "commit_challenge"
            or prior.request_fingerprint != request_hash
            or prior.match_id != match.id
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return match, False, False
    if match.state != Match.State.SETUP or match.room is None:
        raise GameAPIError("challenge_setup_closed", "Challenge setup is not open.")
    if match.room.challenge_source != Room.ChallengeSource.PLAYERS:
        raise GameAPIError("challenge_setup_closed", "This Match uses a system Challenge.")
    if match.setup_expires_at is None or current >= match.setup_expires_at:
        _cancel_setup_locked(match, now=current, reason="setup_timeout")
        return match, False, True
    if Challenge.objects.filter(match=match, creator=creator).exists():
        raise GameAPIError("challenge_already_committed", "A committed Challenge is immutable.")
    solver = (
        Participant.objects.select_for_update().filter(match=match).exclude(pk=creator.pk).first()
    )
    if solver is None:
        raise GameAPIError("invalid_request", "Exactly two participants are required.")
    rules = rules_from_snapshot(match.rules)
    adapter = adapter_for(rules.game_type)
    try:
        encoded = adapter.encode_secret(rules, secret)
    except (GuessValidationError, ColorValidationError) as exc:
        raise GameAPIError(exc.code, "Secret violates the active rules.", status_code=400) from exc
    Challenge.objects.create(
        match=match,
        creator=creator,
        solver=solver,
        protected_secret=encrypt_secret(encoded),
        committed_at=current,
    )
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="commit_challenge",
        request_fingerprint=request_hash,
        match=match,
        room=match.room,
    )
    record_event(
        match=match,
        event_type="challenge.committed",
        visibility="participant",
        participant=creator,
        payload={"participant_id": str(creator.id)},
    )
    committed_count = Challenge.objects.filter(match=match, committed_at__isnull=False).count()
    record_event(
        match=match,
        event_type="challenge.setup_progress",
        visibility="match",
        payload={"committed_count": committed_count, "required_count": 2},
    )
    if committed_count == 2:
        countdown_seconds = settings.FRIENDLY_COUNTDOWN_SECONDS
        started_at = current + timedelta(seconds=countdown_seconds)
        match.state = Match.State.ACTIVE if countdown_seconds == 0 else Match.State.COUNTDOWN
        match.started_at = started_at
        match.deadline = started_at + timedelta(seconds=rules.match_deadline_seconds)
        match.setup_expires_at = None
        match.save(update_fields=["state", "started_at", "deadline", "setup_expires_at"])
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
    return match, True, False


def commit_challenge(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    secret: object,
    now: datetime | None = None,
) -> tuple[Match, bool]:
    match, created, expired = _commit_challenge(
        guest=guest,
        match_id=match_id,
        command_id=command_id,
        secret=secret,
        now=now,
    )
    if expired:
        raise GameAPIError("challenge_setup_expired", "Challenge setup has expired.")
    return match, created
