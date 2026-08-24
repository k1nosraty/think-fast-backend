import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.games.domain import (
    PRESETS,
    GuessValidationError,
    NumberRules,
    evaluate_number,
    validate_sequence,
)
from apps.games.secrets import decrypt_secret, encrypt_secret, generate_number_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import Attempt, Challenge, CommandRecord, Match, Participant, Result
from apps.realtime.publisher import record_event


def fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def rules_from_snapshot(snapshot: dict[str, object]) -> NumberRules:
    return NumberRules(**{field.name: snapshot[field.name] for field in fields(NumberRules)})  # type: ignore[arg-type]


@transaction.atomic
def create_solo(
    *,
    guest: GuestIdentity,
    command_id: uuid.UUID,
    preset_id: str,
    secret_factory: Callable[[NumberRules], str] | None = None,
) -> tuple[Match, bool]:
    GuestIdentity.objects.select_for_update().get(pk=guest.pk)
    request_hash = fingerprint({"preset_id": preset_id})
    prior = (
        CommandRecord.objects.select_related("match")
        .filter(guest=guest, command_id=command_id)
        .first()
    )
    if prior:
        if (
            prior.operation != "create_solo"
            or prior.request_fingerprint != request_hash
            or prior.match is None
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return prior.match, False
    rules = PRESETS.get(preset_id)
    if rules is None:
        raise GameAPIError("invalid_request", "Unknown preset_id.", status_code=400)
    now = timezone.now()
    match = Match.objects.create(
        rules=rules.snapshot(),
        started_at=now,
        deadline=now + timedelta(seconds=rules.match_deadline_seconds),
        latest_sequence=1,
    )
    Participant.objects.create(
        match=match,
        guest=guest,
        display_name=guest.display_name,
        avatar_id=guest.avatar_id,
        connected=True,
    )
    factory = secret_factory or generate_number_secret
    Challenge.objects.create(match=match, protected_secret=encrypt_secret(factory(rules)))
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="create_solo",
        request_fingerprint=request_hash,
        match=match,
    )
    return match, True


def _finish(
    match: Match,
    participant: Participant,
    *,
    outcome: str,
    reason: str,
    now: datetime,
    reveal: bool,
) -> None:
    match.state = Match.State.FINISHED
    match.finished_at = now
    match.latest_sequence += 1
    match.save(update_fields=["state", "finished_at", "latest_sequence"])
    Result.objects.create(
        match=match,
        outcome=outcome,
        reason=reason,
        winner_participant_ids=[str(participant.id)] if outcome == "won" else [],
        secret_revealed=reveal,
    )


def _finish_friendly(match: Match, *, reason: str, now: datetime) -> None:
    participants = list(match.participants.select_for_update())
    solved = [item for item in participants if item.solve_state == Participant.SolveState.SOLVED]
    winners: list[Participant] = []
    outcome = "draw"
    if solved:
        fewest = min(item.attempt_count for item in solved)
        contenders = [item for item in solved if item.attempt_count == fewest]
        contenders.sort(key=lambda item: item.solved_at or now)
        winners = [contenders[0]]
        if len(contenders) > 1:
            first_at = contenders[0].solved_at or now
            second_at = contenders[1].solved_at or now
            if (second_at - first_at).total_seconds() <= 0.5:
                winners = contenders
                outcome = "draw"
            else:
                outcome = "won"
        else:
            outcome = "won"
    for item in participants:
        if item.solve_state == Participant.SolveState.PLAYING:
            item.solve_state = Participant.SolveState.UNSOLVED
            item.save(update_fields=["solve_state"])
    match.state = Match.State.FINISHED
    match.finished_at = now
    match.finish_due_at = None
    match.save(update_fields=["state", "finished_at", "finish_due_at"])
    result = Result.objects.create(
        match=match,
        outcome=outcome,
        reason=reason,
        winner_participant_ids=[str(item.id) for item in winners],
        secret_revealed=True,
    )
    record_event(
        match=match,
        event_type="match.finished",
        visibility="match",
        payload={
            "outcome": result.outcome,
            "winner_participant_ids": result.winner_participant_ids,
            "reason": result.reason,
            "secret_revealed": True,
        },
    )


def _activate_countdown(match: Match, now: datetime) -> None:
    if match.state != Match.State.COUNTDOWN or now < match.started_at:
        return
    match.state = Match.State.ACTIVE
    match.save(update_fields=["state"])
    record_event(
        match=match,
        event_type="match.started",
        visibility="match",
        payload={
            "started_at": match.started_at.isoformat().replace("+00:00", "Z"),
            "deadline": match.deadline.isoformat().replace("+00:00", "Z"),
        },
    )


@transaction.atomic
def activate_countdown(match_id: uuid.UUID, now: datetime | None = None) -> None:
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is not None:
        _activate_countdown(match, now or timezone.now())


@transaction.atomic
def _submit_guess(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    guess: str,
    now: datetime | None = None,
) -> tuple[Attempt | None, Match, bool]:
    now = now or timezone.now()
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)
    participant = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )
    request_hash = fingerprint({"guess": guess})
    prior = Attempt.objects.filter(participant=participant, command_id=command_id).first()
    if prior:
        if prior.request_fingerprint != request_hash:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different Guess."
            )
        return prior, match, False
    _activate_countdown(match, now)
    if match.state not in {Match.State.ACTIVE, Match.State.FINISHING}:
        raise GameAPIError("match_not_active", "Match is not active.")
    rules = rules_from_snapshot(match.rules)
    if participant.solve_state != Participant.SolveState.PLAYING:
        raise GameAPIError("match_not_active", "Participant is no longer accepting guesses.")
    if match.state == Match.State.FINISHING and match.finish_due_at and now > match.finish_due_at:
        _finish_friendly(match, reason="solved", now=now)
        return None, match, False
    if now >= match.deadline:
        if rules.match_mode == "friendly":
            _finish_friendly(match, reason="deadline", now=now)
        else:
            participant.solve_state = Participant.SolveState.UNSOLVED
            participant.save(update_fields=["solve_state"])
            _finish(match, participant, outcome="unsolved", reason="deadline", now=now, reveal=True)
        return None, match, False
    if participant.attempt_count >= rules.attempt_limit:
        raise GameAPIError("attempt_limit_reached", "Attempt limit has been reached.")
    try:
        validate_sequence(guess, rules)
    except GuessValidationError as exc:
        raise GameAPIError(exc.code, "Guess violates the active rules.", status_code=400) from exc
    secret = decrypt_secret(match.challenge.protected_secret)
    positions, solved = evaluate_number(rules=rules, secret=secret, guess=guess)
    participant.attempt_count += 1
    participant.solve_state = (
        Participant.SolveState.SOLVED if solved else Participant.SolveState.PLAYING
    )
    participant.solved_at = now if solved else None
    participant.save(update_fields=["attempt_count", "solve_state", "solved_at"])
    if rules.match_mode == "practice":
        match.latest_sequence += 1
        match.save(update_fields=["latest_sequence"])
    attempt = Attempt.objects.create(
        participant=participant,
        command_id=command_id,
        request_fingerprint=request_hash,
        ordinal=participant.attempt_count,
        guess=guess,
        feedback={"kind": "positional", "positions": positions},
        solved=solved,
        accepted_at=now,
    )
    if rules.match_mode == "friendly":
        record_event(
            match=match,
            event_type="guess.evaluated",
            visibility="participant",
            participant=participant,
            payload={
                "participant_id": str(participant.id),
                "attempt_id": str(attempt.id),
                "ordinal": attempt.ordinal,
                "feedback": attempt.feedback,
                "solved": solved,
            },
        )
        record_event(
            match=match,
            event_type="opponent.guessed",
            visibility="match",
            participant=participant,
            payload={"participant_id": str(participant.id), "attempt_count": attempt.ordinal},
        )
    if solved and rules.match_mode == "practice":
        _finish(match, participant, outcome="won", reason="solved", now=now, reveal=True)
    elif solved:
        record_event(
            match=match,
            event_type="participant.solved",
            visibility="match",
            payload={"participant_id": str(participant.id), "attempt_count": attempt.ordinal},
        )
        other_solved = (
            Participant.objects.filter(match=match, solve_state=Participant.SolveState.SOLVED)
            .exclude(pk=participant.pk)
            .exists()
        )
        if other_solved:
            _finish_friendly(match, reason="solved", now=now)
        elif match.state == Match.State.ACTIVE:
            match.state = Match.State.FINISHING
            match.finish_due_at = now + timedelta(milliseconds=500)
            match.save(update_fields=["state", "finish_due_at"])
    elif participant.attempt_count == rules.attempt_limit:
        participant.solve_state = Participant.SolveState.UNSOLVED
        participant.save(update_fields=["solve_state"])
        if rules.match_mode == "practice":
            _finish(
                match, participant, outcome="unsolved", reason="attempt_limit", now=now, reveal=True
            )
        elif not Participant.objects.filter(
            match=match, solve_state=Participant.SolveState.PLAYING
        ).exists():
            _finish_friendly(match, reason="attempt_limit", now=now)
    return attempt, match, True


def submit_guess(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    guess: str,
    now: datetime | None = None,
) -> tuple[Attempt, Match, bool]:
    attempt, match, created = _submit_guess(
        guest=guest, match_id=match_id, command_id=command_id, guess=guess, now=now
    )
    if attempt is None:
        if hasattr(match, "result") and match.result.reason == "deadline":
            raise GameAPIError("deadline_elapsed", "Match deadline has elapsed.")
        raise GameAPIError("match_not_active", "Match is no longer accepting guesses.")
    return attempt, match, created


@transaction.atomic
def refresh_match_state(
    *, guest: GuestIdentity, match_id: uuid.UUID, now: datetime | None = None
) -> Match:
    now = now or timezone.now()
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)
    participant = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )
    _activate_countdown(match, now)
    rules = rules_from_snapshot(match.rules)
    if match.state in {Match.State.ACTIVE, Match.State.FINISHING} and now >= match.deadline:
        if rules.match_mode == "friendly":
            _finish_friendly(match, reason="deadline", now=now)
        else:
            participant.solve_state = Participant.SolveState.UNSOLVED
            participant.save(update_fields=["solve_state"])
            _finish(match, participant, outcome="unsolved", reason="deadline", now=now, reveal=True)
    elif match.state == Match.State.FINISHING and match.finish_due_at and now > match.finish_due_at:
        _finish_friendly(match, reason="solved", now=now)
    return match


@transaction.atomic
def abandon(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    now: datetime | None = None,
) -> Match:
    now = now or timezone.now()
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)
    participant = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )
    request_hash = fingerprint({})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if (
            prior.operation != "abandon"
            or prior.request_fingerprint != request_hash
            or prior.match_id != match.id
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return match
    if match.state in {Match.State.COUNTDOWN, Match.State.ACTIVE, Match.State.FINISHING}:
        participant.solve_state = Participant.SolveState.ABANDONED
        participant.save(update_fields=["solve_state"])
        match.state = Match.State.ABANDONED
        match.finished_at = now
        match.finish_due_at = None
        match.save(update_fields=["state", "finished_at", "finish_due_at"])
        winner_ids = (
            [
                str(item)
                for item in match.participants.exclude(pk=participant.pk).values_list(
                    "id", flat=True
                )
            ]
            if match.rules.get("match_mode") == "friendly"
            else []
        )
        result = Result.objects.create(
            match=match,
            outcome="abandoned",
            reason="abandoned",
            winner_participant_ids=winner_ids,
            secret_revealed=False,
        )
        if match.rules.get("match_mode") == "friendly":
            record_event(
                match=match,
                event_type="match.finished",
                visibility="match",
                payload={
                    "outcome": result.outcome,
                    "winner_participant_ids": winner_ids,
                    "reason": result.reason,
                    "secret_revealed": False,
                },
            )
    elif match.state != Match.State.ABANDONED:
        raise GameAPIError("match_not_active", "Only an active match can be abandoned.")
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="abandon",
        request_fingerprint=request_hash,
        match=match,
    )
    return match
