"""Party game mode service: One Creator -> Multiple Guessers with round rotation."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.analytics.service import record_analytics
from apps.games.base import GameValidationError
from apps.games.registry import adapter_for, rules_from_snapshot
from apps.games.secrets import decrypt_secret, encrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.idempotency import check_command_prior, fingerprint
from apps.matches.models import (
    Attempt,
    Challenge,
    CommandRecord,
    Match,
    Participant,
    Result,
    Room,
    RoomMembership,
)
from apps.realtime.publisher import record_event

GUESSER_POINTS = [100, 75, 50, 25]
CREATOR_UNSOLVED_REWARD = 80
CREATOR_PER_UNSOLVED_BONUS = 20
CREATOR_MINIMUM_POINTS = 20
DEFAULT_ROUND_DURATION_SECONDS = 60
DEFAULT_SETUP_DURATION_SECONDS = 90
PARTY_MINIMUM_ACTIVE_PLAYERS = 3

# Configurable via settings, with fallbacks to defaults for backward compatibility
def _party_setup_seconds() -> int:
    return int(getattr(settings, "PARTY_SETUP_DURATION_SECONDS", DEFAULT_SETUP_DURATION_SECONDS))


def _party_round_seconds() -> int:
    return int(getattr(settings, "PARTY_ROUND_DURATION_SECONDS", DEFAULT_ROUND_DURATION_SECONDS))


def is_party_match(match: Match) -> bool:
    if match.room_id is None:
        return False
    return Room.objects.filter(pk=match.room_id, room_mode="party").exists()


def get_current_round_challenge(match: Match) -> Challenge | None:
    return Challenge.objects.filter(
        match=match, round_number=match.round_number, solver__isnull=True
    ).first()


def pick_next_creator(
    match: Match,
    exclude_participant: Participant | None = None,
    now: datetime | None = None,
) -> Participant | None:
    if match.room:
        member_guest_ids = list(
            match.room.memberships.order_by("joined_at").values_list("guest_id", flat=True)
        )
        all_participants = list(match.participants.all())
        participants = [
            p for gid in member_guest_ids for p in all_participants if p.guest_id == gid
        ]
    else:
        participants = list(match.participants.all())

    current_time = now or timezone.now()
    participants = [
        participant
        for participant in participants
        if participant.solve_state != Participant.SolveState.ABANDONED
        and (
            participant.connected
            or participant.grace_expires_at is None
            or participant.grace_expires_at > current_time
        )
    ]
    if not participants:
        return None

    if match.creator is None:
        return participants[0]

    current_id = match.creator_id
    current_index = -1
    for idx, p in enumerate(participants):
        if p.id == current_id:
            current_index = idx
            break

    if current_index == -1:
        return participants[0]

    next_index = (current_index + 1) % len(participants)
    return participants[next_index]


@transaction.atomic
def commit_party_secret(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    secret: Any,
    now: datetime | None = None,
) -> tuple[Match, bool]:
    current = now or timezone.now()
    match = (
        Match.objects.select_for_update(of=("self",))
        .select_related("room")
        .filter(pk=match_id)
        .first()
    )
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)

    creator = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if creator is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )

    if match.creator_id != creator.id and not creator.is_creator:
        raise GameAPIError(
            "not_creator", "Only the current round creator can submit the secret.", status_code=403
        )

    request_hash = fingerprint(
        {"match_id": str(match_id), "round": match.round_number, "secret": secret}
    )
    prior = check_command_prior(
        guest=guest,
        command_id=command_id,
        operation="commit_party_secret",
        request_hash=request_hash,
    )
    if prior is not None:
        return match, False

    if match.state != Match.State.SETUP or match.round_state != "creator_setup":
        raise GameAPIError("challenge_setup_closed", "Secret creation is not open.")

    rules = rules_from_snapshot(match.rules)
    adapter = adapter_for(rules.game_type)
    try:
        encoded = adapter.encode_secret(rules, secret)
    except GameValidationError as exc:
        raise GameAPIError(exc.code, "Secret violates the active rules.", status_code=400) from exc

    existing = Challenge.objects.filter(
        match=match, round_number=match.round_number, solver__isnull=True
    ).first()
    if existing:
        raise GameAPIError(
            "challenge_already_committed", "A secret for this round is already committed."
        )

    Challenge.objects.create(
        match=match,
        round_number=match.round_number,
        creator=creator,
        solver=None,
        protected_secret=encrypt_secret(encoded),
        committed_at=current,
    )

    countdown_seconds = getattr(settings, "FRIENDLY_COUNTDOWN_SECONDS", 5)
    round_duration = getattr(rules, "match_deadline_seconds", _party_round_seconds())
    started_at = current + timedelta(seconds=countdown_seconds)
    deadline = started_at + timedelta(seconds=round_duration)

    match.state = Match.State.COUNTDOWN if countdown_seconds > 0 else Match.State.ACTIVE
    match.round_state = "countdown" if countdown_seconds > 0 else "active"
    match.started_at = started_at
    match.deadline = deadline
    match.setup_expires_at = None
    match.save(update_fields=["state", "round_state", "started_at", "deadline", "setup_expires_at"])

    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="commit_party_secret",
        request_fingerprint=request_hash,
        match=match,
        room=match.room,
    )

    record_event(
        match=match,
        event_type="challenge.committed",
        visibility="match",
        payload={"creator_participant_id": str(creator.id), "round_number": match.round_number},
    )
    record_event(
        match=match,
        event_type="match.countdown_started",
        visibility="match",
        payload={"countdown_seconds": countdown_seconds, "round_number": match.round_number},
    )
    if countdown_seconds == 0:
        record_event(
            match=match,
            event_type="round.started",
            visibility="match",
            payload={
                "round_number": match.round_number,
                "started_at": started_at.isoformat().replace("+00:00", "Z"),
                "deadline": deadline.isoformat().replace("+00:00", "Z"),
            },
        )
    return match, True


def calculate_and_apply_scores(match: Match, reason: str, now: datetime) -> dict[str, Any]:
    rules = rules_from_snapshot(match.rules)
    solvers = list(
        match.participants.filter(solve_state=Participant.SolveState.SOLVED).order_by(
            "solved_at", "attempt_count"
        )
    )
    creator = match.creator
    unsolved_qs = match.participants.filter(
        solve_state__in=[Participant.SolveState.PLAYING, Participant.SolveState.UNSOLVED]
    )
    if creator is not None:
        unsolved_qs = unsolved_qs.exclude(pk=creator.pk)
    unsolved_count = unsolved_qs.count()

    solver_records: list[dict[str, Any]] = []
    for idx, solver in enumerate(solvers):
        pts = GUESSER_POINTS[idx] if idx < len(GUESSER_POINTS) else GUESSER_POINTS[-1]
        solver.round_score = pts
        solver.score += pts
        solver.round_rank = idx + 1
        solver.save(update_fields=["round_score", "score", "round_rank"])
        duration_ms = (
            max(0, int((solver.solved_at - match.started_at).total_seconds() * 1000))
            if solver.solved_at
            else 0
        )
        solver_records.append(
            {
                "participant_id": str(solver.id),
                "display_name": solver.display_name,
                "rank": idx + 1,
                "round_score": pts,
                "total_score": solver.score,
                "solve_duration_ms": duration_ms,
            }
        )

    creator_pts = CREATOR_MINIMUM_POINTS
    if creator is not None:
        if len(solvers) == 0:
            creator_pts = CREATOR_UNSOLVED_REWARD
        else:
            first_solve_secs = (
                (solvers[0].solved_at - match.started_at).total_seconds()
                if solvers[0].solved_at
                else 0
            )
            challenge_bonus = unsolved_count * CREATOR_PER_UNSOLVED_BONUS
            if first_solve_secs >= 20:
                creator_pts = max(CREATOR_MINIMUM_POINTS, 30 + challenge_bonus)
            else:
                creator_pts = max(CREATOR_MINIMUM_POINTS, challenge_bonus)
        creator.round_score = creator_pts
        creator.score += creator_pts
        creator.save(update_fields=["round_score", "score"])

    for non_solver in match.participants.filter(
        solve_state__in=[Participant.SolveState.PLAYING, Participant.SolveState.UNSOLVED]
    ):
        if creator and non_solver.id == creator.id:
            continue
        non_solver.solve_state = Participant.SolveState.UNSOLVED
        non_solver.round_score = 0
        non_solver.save(update_fields=["solve_state", "round_score"])

    revealed_secret = None
    challenge = get_current_round_challenge(match)
    if challenge is not None:
        decrypted = decrypt_secret(challenge.protected_secret)
        revealed_secret = adapter_for(rules.game_type).decode_secret(rules, decrypted)

    scores_map = {str(p.id): p.score for p in match.participants.all()}

    return {
        "round_number": match.round_number,
        "total_rounds": match.total_rounds,
        "reason": reason,
        "solvers": solver_records,
        "creator": {
            "participant_id": str(creator.id) if creator else None,
            "display_name": creator.display_name if creator else "",
            "round_score": creator_pts,
            "total_score": creator.score if creator else 0,
        }
        if creator
        else None,
        "revealed_secret": revealed_secret,
        "scores": scores_map,
    }


@transaction.atomic
def finish_party_round(match: Match, *, reason: str, now: datetime | None = None) -> Match:
    current = now or timezone.now()
    if match.round_state in {"round_finished", "match_finished"}:
        return match

    match.state = Match.State.FINISHED
    match.round_state = "round_finished"
    match.finished_at = current
    match.finish_due_at = None
    match.save(update_fields=["state", "round_state", "finished_at", "finish_due_at"])

    round_summary = calculate_and_apply_scores(match, reason, current)

    Result.objects.update_or_create(
        match=match,
        defaults={
            "outcome": "won" if round_summary["solvers"] else "unsolved",
            "reason": reason,
            "winner_participant_ids": [s["participant_id"] for s in round_summary["solvers"]],
            "secret_revealed": True,
        },
    )

    record_event(
        match=match,
        event_type="round.finished",
        visibility="match",
        payload=round_summary,
    )
    record_event(
        match=match,
        event_type="scores.updated",
        visibility="match",
        payload={"scores": round_summary["scores"], "round_number": match.round_number},
    )
    return match


def _party_active_players(match: Match) -> int:
    return match.participants.exclude(solve_state=Participant.SolveState.ABANDONED).count()


@transaction.atomic
def _terminate_party_match(match: Match, *, reason: str, now: datetime) -> None:
    """Terminate the whole party match with a terminal outcome, keeping the
    secret unrevealed and releasing the room back to the ready check."""
    match.state = Match.State.ABANDONED
    match.round_state = "match_finished"
    match.finished_at = now
    match.finish_due_at = None
    match.save(update_fields=["state", "round_state", "finished_at", "finish_due_at"])
    active_ids = [
        str(item.id)
        for item in match.participants.exclude(solve_state=Participant.SolveState.ABANDONED)
    ]
    Result.objects.update_or_create(
        match=match,
        defaults={
            "outcome": "abandoned",
            "reason": reason,
            "winner_participant_ids": active_ids,
            "secret_revealed": False,
        },
    )
    if match.room_id:
        room = Room.objects.select_for_update().get(pk=match.room_id)
        room.state = Room.State.READY_CHECK
        room.save(update_fields=["state", "updated_at"])
        RoomMembership.objects.filter(room=room).update(ready=False)
    record_event(
        match=match,
        event_type="match.finished",
        visibility="match",
        payload={
            "outcome": "abandoned",
            "winner_participant_ids": active_ids,
            "reason": reason,
            "secret_revealed": False,
        },
    )
    record_analytics(
        "match_completed",
        match_id=match.id,
        room_id=match.room_id,
        preset_id=str(match.rules["preset_id"]),
        outcome="abandoned",
        reason=reason,
        solve_duration_ms=max(0, int((now - match.started_at).total_seconds() * 1000)),
    )


@transaction.atomic
def _reassign_current_round_creator(match: Match, now: datetime) -> Participant | None:
    """Hand the current round's creator role to the next eligible player after
    the departing creator and reset the setup window so the round can proceed."""
    successor = pick_next_creator(match, exclude_participant=match.creator, now=now)
    if successor is None:
        return None
    previous = match.creator
    match.creator = successor
    match.setup_expires_at = now + timedelta(seconds=_party_setup_seconds())
    match.save(update_fields=["creator", "setup_expires_at"])
    if previous is not None:
        previous.is_creator = False
        previous.save(update_fields=["is_creator"])
    successor.is_creator = True
    successor.save(update_fields=["is_creator"])
    record_event(
        match=match,
        event_type="creator.rotated",
        visibility="match",
        payload={
            "new_creator_participant_id": str(successor.id),
            "new_creator_display_name": successor.display_name,
            "round_number": match.round_number,
        },
    )
    record_event(
        match=match,
        event_type="challenge.setup_started",
        visibility="match",
        payload={
            "expires_at": match.setup_expires_at.isoformat().replace("+00:00", "Z"),
            "creator_participant_id": str(successor.id),
            "required_count": 1,
        },
    )
    return successor


@transaction.atomic
def abandon_party_participant(match: Match, participant: Participant, *, now: datetime) -> None:
    """Absorb a party participant who leaves or loses the disconnect grace.

    - A single departure never abandons the whole match while enough players
      remain (``PARTY_MINIMUM_ACTIVE_PLAYERS``).
    - The creator leaving during creator setup is replaced by the next eligible
      player and the setup window resets; the architect never strands the round.
    - The creator leaving after the secret is committed leaves the committed
      round to run to its normal finish.
    - The last PLAYING guesser leaving finishes the round.
    """
    if participant.solve_state != Participant.SolveState.PLAYING:
        return
    participant.solve_state = Participant.SolveState.ABANDONED
    participant.save(update_fields=["solve_state"])
    record_analytics(
        "participant_abandoned",
        match_id=match.id,
        room_id=match.room_id,
        preset_id=str(match.rules["preset_id"]),
        reason="abandoned",
    )
    if _party_active_players(match) < PARTY_MINIMUM_ACTIVE_PLAYERS:
        _terminate_party_match(match, reason="not_enough_players", now=now)
        return
    if match.round_state == "creator_setup":
        if match.creator_id == participant.id:
            _reassign_current_round_creator(match, now=now)
        return
    if match.state in {
        Match.State.COUNTDOWN,
        Match.State.ACTIVE,
        Match.State.FINISHING,
    }:
        if match.creator_id == participant.id:
            return
        remaining_guessers = Participant.objects.filter(
            match=match, solve_state=Participant.SolveState.PLAYING
        )
        if match.creator_id is not None:
            remaining_guessers = remaining_guessers.exclude(pk=match.creator_id)
        if not remaining_guessers.exists():
            finish_party_round(match, reason="abandoned", now=now)


@transaction.atomic
def submit_party_guess(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    guess: Any,
    now: datetime | None = None,
) -> tuple[Attempt, Match, bool]:
    current = now or timezone.now()
    match = Match.objects.select_for_update().filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)

    participant = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )

    if participant.is_creator or (match.creator_id == participant.id):
        raise GameAPIError(
            "creator_cannot_guess", "The creator cannot guess in their own round.", status_code=403
        )

    request_hash = fingerprint({"guess": guess})
    prior = Attempt.objects.filter(participant=participant, command_id=command_id).first()
    if prior:
        if prior.request_fingerprint != request_hash:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different Guess."
            )
        return prior, match, False

    if match.state == Match.State.COUNTDOWN and current >= match.started_at:
        match.state = Match.State.ACTIVE
        match.round_state = "active"
        match.save(update_fields=["state", "round_state"])
        record_event(
            match=match,
            event_type="round.started",
            visibility="match",
            payload={
                "round_number": match.round_number,
                "started_at": match.started_at.isoformat().replace("+00:00", "Z"),
                "deadline": match.deadline.isoformat().replace("+00:00", "Z"),
            },
        )

    if match.round_state != "active":
        raise GameAPIError("match_not_active", "Round is not currently accepting guesses.")

    if participant.solve_state != Participant.SolveState.PLAYING:
        raise GameAPIError("match_not_active", "You have already solved or ended this round.")

    rules = rules_from_snapshot(match.rules)
    if participant.attempt_count >= rules.attempt_limit:
        raise GameAPIError("attempt_limit_reached", "Attempt limit has been reached.")

    if current >= match.deadline:
        finish_party_round(match, reason="deadline", now=current)
        raise GameAPIError("deadline_elapsed", "Round deadline has elapsed.")

    adapter = adapter_for(rules.game_type)
    challenge = get_current_round_challenge(match)
    if challenge is None:
        raise GameAPIError("challenge_not_committed", "The creator secret has not been committed.")

    serialized_secret = decrypt_secret(challenge.protected_secret)
    secret = adapter.decode_secret(rules, serialized_secret)

    try:
        canonical_guess, feedback, solved = adapter.evaluate(rules, secret, guess)
    except GameValidationError as exc:
        raise GameAPIError(exc.code, "Guess violates the active rules.", status_code=400) from exc

    participant.attempt_count += 1
    if solved:
        participant.solve_state = Participant.SolveState.SOLVED
        participant.solved_at = current
    participant.save(update_fields=["attempt_count", "solve_state", "solved_at"])

    attempt = Attempt.objects.create(
        participant=participant,
        round_number=match.round_number,
        command_id=command_id,
        request_fingerprint=request_hash,
        ordinal=participant.attempt_count,
        guess=canonical_guess,
        feedback=feedback,
        solved=solved,
        accepted_at=current,
    )

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
            "round_number": match.round_number,
        },
    )
    record_event(
        match=match,
        event_type="opponent.guessed",
        visibility="match",
        participant=participant,
        payload={
            "participant_id": str(participant.id),
            "attempt_count": attempt.ordinal,
            "round_number": match.round_number,
        },
    )

    if solved:
        record_event(
            match=match,
            event_type="player.solved",
            visibility="match",
            payload={
                "participant_id": str(participant.id),
                "display_name": participant.display_name,
                "attempt_count": attempt.ordinal,
                "solve_duration_ms": max(
                    0, int((current - match.started_at).total_seconds() * 1000)
                ),
                "round_number": match.round_number,
            },
        )
        # Keep the round open while another guesser can still solve. This is
        # what preserves placement scoring (1st/2nd/3rd) and lets concurrent
        # submissions race against the same authoritative round.
        remaining_guessers = Participant.objects.filter(
            match=match,
            solve_state=Participant.SolveState.PLAYING,
        )
        if match.creator_id is not None:
            remaining_guessers = remaining_guessers.exclude(pk=match.creator_id)
        if not remaining_guessers.exists():
            finish_party_round(match, reason="solved", now=current)

    return attempt, match, True


@transaction.atomic
def advance_party_round(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    now: datetime | None = None,
) -> Match:
    current = now or timezone.now()
    match = (
        Match.objects.select_for_update(of=("self",))
        .select_related("room")
        .filter(pk=match_id)
        .first()
    )
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)

    # The command must replay identically after the transition changes the
    # current round number.
    request_hash = fingerprint({"match_id": str(match_id)})
    prior = check_command_prior(
        guest=guest,
        command_id=command_id,
        operation="next_round",
        request_hash=request_hash,
    )
    if prior is not None:
        if prior.match_id != match.id:
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        return match

    caller = Participant.objects.select_for_update().filter(match=match, guest=guest).first()
    if caller is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )

    if match.round_state != "round_finished":
        raise GameAPIError("not_ready", "Current round has not finished.")

    if match.round_number >= match.total_rounds:
        match.state = Match.State.FINISHED
        match.round_state = "match_finished"
        match.save(update_fields=["state", "round_state"])
        record_event(
            match=match,
            event_type="match.finished",
            visibility="match",
            payload={
                "outcome": "finished",
                "final_scores": {str(p.id): p.score for p in match.participants.all()},
                "total_rounds": match.total_rounds,
            },
        )
        if match.room_id:
            room = Room.objects.select_for_update().get(pk=match.room_id)
            room.state = Room.State.READY_CHECK
            room.save(update_fields=["state", "updated_at"])
            RoomMembership.objects.filter(room=room).update(ready=False)
        CommandRecord.objects.create(
            guest=guest,
            command_id=command_id,
            operation="next_round",
            request_fingerprint=request_hash,
            match=match,
            room=match.room,
        )
        return match

    next_creator = pick_next_creator(match, exclude_participant=match.creator, now=current)
    if next_creator is None:
        raise GameAPIError("no_players", "No active players remaining.")

    match.round_number += 1
    match.creator = next_creator
    match.state = Match.State.SETUP
    match.round_state = "creator_setup"
    match.setup_expires_at = current + timedelta(seconds=_party_setup_seconds())
    match.save(
        update_fields=["round_number", "creator", "state", "round_state", "setup_expires_at"]
    )

    for p in match.participants.all():
        p.is_creator = p.id == next_creator.id
        p.solve_state = Participant.SolveState.PLAYING
        p.attempt_count = 0
        p.round_score = 0
        p.round_rank = None
        p.solved_at = None
        p.save(
            update_fields=[
                "is_creator",
                "solve_state",
                "attempt_count",
                "round_score",
                "round_rank",
                "solved_at",
            ]
        )

    record_event(
        match=match,
        event_type="creator.rotated",
        visibility="match",
        payload={
            "new_creator_participant_id": str(next_creator.id),
            "new_creator_display_name": next_creator.display_name,
            "round_number": match.round_number,
        },
    )
    record_event(
        match=match,
        event_type="round.created",
        visibility="match",
        payload={
            "round_number": match.round_number,
            "total_rounds": match.total_rounds,
            "creator_participant_id": str(next_creator.id),
            "creator_display_name": next_creator.display_name,
            "expires_at": match.setup_expires_at.isoformat().replace("+00:00", "Z"),
        },
    )
    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="next_round",
        request_fingerprint=request_hash,
        match=match,
        room=match.room,
    )
    return match
