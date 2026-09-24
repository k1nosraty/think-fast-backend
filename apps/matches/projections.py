from datetime import datetime

from django.db.models import Prefetch
from django.utils import timezone

from apps import CONTRACT_VERSION
from apps.accounts.models import GuestIdentity
from apps.games.registry import adapter_for, rules_from_snapshot
from apps.games.secrets import decrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import Attempt, Challenge, Match, Participant, Result
from apps.matches.party import is_party_match


def iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def snapshot(match: Match, guest: GuestIdentity) -> dict[str, object]:
    match_id = match.pk
    participant = (
        Participant.objects.select_related("match")
        .prefetch_related(Prefetch("attempts", queryset=Attempt.objects.order_by("ordinal")))
        .filter(match_id=match_id, guest=guest)
        .first()
    )
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )
    # One fresh read with room/creator joined instead of refresh + lazy joins.
    # Callers pass a possibly-stale instance after a write transaction.
    fresh = Match.objects.select_related("room", "creator").filter(pk=match_id).first()
    assert fresh is not None
    match = fresh
    # Re-point the participant's cached match so is_party_match() and later
    # reads do not trigger an extra query.
    participant.match = match
    rules = rules_from_snapshot(match.rules)
    history = rules.history_policy
    is_party = is_party_match(match)
    # The attempts are already prefetched above; filter in Python so the
    # prefetch is actually used instead of issuing a second query.
    prefetched_attempts = list(participant.attempts.all())
    if is_party:
        attempt_rows = [a for a in prefetched_attempts if a.round_number == match.round_number]
    else:
        attempt_rows = prefetched_attempts
    if history.get("type") == "last_n":
        count = history.get("count", 1)
        attempt_rows = attempt_rows[-(count if isinstance(count, int) else 1) :]
    elif history.get("type") == "none":
        attempt_rows = []
    attempts = [
        {
            "attempt_id": str(item.id),
            "ordinal": item.ordinal,
            "guess": item.guess,
            "feedback": item.feedback,
            "accepted_at": iso(item.accepted_at),
            "solved": item.solved,
        }
        for item in attempt_rows
    ]
    try:
        result_obj: Result | None = match.result
    except Result.DoesNotExist:
        result_obj = None
    # Single Challenge query for everything below (reveal + setup + actions).
    # The table is tiny per match (1 shared or ≤2 duel challenges), so one
    # fetch in Python replaces up to 6 sequential EXISTS/COUNT/FIRST queries.
    challenges = list(Challenge.objects.filter(match_id=match.pk))
    round_challenges = [c for c in challenges if c.round_number == match.round_number]
    shared_round_challenge = next((c for c in round_challenges if c.solver_id is None), None)
    own_challenge = next(
        (c for c in challenges if c.creator_id == participant.id),
        None,
    )
    own_round_challenge = next(
        (c for c in round_challenges if c.creator_id == participant.id),
        None,
    )
    result = None
    if result_obj is not None and (
        not is_party or match.round_state in {"round_finished", "match_finished"}
    ):
        outcome = result_obj.outcome
        if outcome == "won" and str(participant.id) not in result_obj.winner_participant_ids:
            outcome = "lost"
        result = {
            "outcome": outcome,
            "winner_participant_ids": result_obj.winner_participant_ids,
            "reason": result_obj.reason,
            "secret_revealed": result_obj.secret_revealed,
        }
        if result_obj.secret_revealed:
            challenge = (
                shared_round_challenge
                or next((c for c in challenges if c.solver_id == participant.id), None)
                or next((c for c in challenges if c.solver_id is None), None)
            )
            if challenge is not None and challenge.secret_destroyed_at is None:
                result["revealed_secret"] = adapter_for(rules.game_type).decode_secret(
                    rules, decrypt_secret(challenge.protected_secret)
                )
            else:
                result["secret_revealed"] = False
    actions = []
    if match.state == Match.State.ACTIVE:
        if not is_party or (match.round_state == "active" and not participant.is_creator):
            actions.append("submit_guess")
        actions.append("leave")
    elif match.state == Match.State.SETUP:
        if is_party:
            if participant.is_creator:
                actions.extend(["commit_challenge", "leave"])
            else:
                actions.append("leave")
        else:
            actions = ["leave"] if own_challenge is not None else ["commit_challenge", "leave"]
    elif match.round_state == "round_finished":
        if is_party and match.round_number < match.total_rounds:
            actions.append("next_round")
        if match.room_id:
            actions.append("request_rematch")
        actions.append("leave")
    elif match.state in {Match.State.FINISHED, Match.State.ABANDONED}:
        if match.room_id:
            actions.append("request_rematch")

    setup = None
    if match.state == Match.State.SETUP:
        if is_party:
            own_commit = own_round_challenge is not None
            committed_count = 1 if any(c.committed_at is not None for c in round_challenges) else 0
            setup = {
                "expires_at": iso(match.setup_expires_at),
                "own_challenge_committed": own_commit,
                "committed_count": committed_count,
                "required_count": 1,
                "is_creator": participant.is_creator,
                "creator_participant_id": str(match.creator_id) if match.creator_id else None,
            }
        else:
            committed_count = sum(1 for c in challenges if c.committed_at is not None)
            setup = {
                "expires_at": iso(match.setup_expires_at),
                "own_challenge_committed": own_challenge is not None,
                "committed_count": committed_count,
                "required_count": 2,
            }
    participants = list(match.participants.all())
    if result is not None and result_obj is not None and result_obj.winner_participant_ids:
        winner = next(
            (item for item in participants if str(item.id) in result_obj.winner_participant_ids),
            None,
        )
        result["winner_solve_duration_seconds"] = (
            max(0, int((winner.solved_at - match.started_at).total_seconds()))
            if winner is not None and winner.solved_at is not None
            else None
        )
    role = "host" if match.room is not None and match.room.host_id == guest.id else "player"
    return {
        "contract_version": CONTRACT_VERSION,
        "match_id": str(match.id),
        "room_id": str(match.room_id) if match.room_id else None,
        "state": match.state,
        "round_state": match.round_state,
        "round_number": match.round_number,
        "total_rounds": match.total_rounds,
        "creator_participant_id": str(match.creator_id) if match.creator_id else None,
        "scores": {str(item.id): item.score for item in participants},
        "rules": match.rules,
        "server_time": iso(timezone.now()),
        "started_at": iso(match.started_at),
        "finished_at": iso(match.finished_at),
        "deadline": iso(match.deadline),
        "viewer": {
            "participant_id": str(participant.id),
            "display_name": participant.display_name,
            "role": role,
        },
        "participants": [
            {
                "participant_id": str(item.id),
                "display_name": item.display_name,
                "avatar_id": item.avatar_id,
                "connection_state": "abandoned"
                if item.solve_state == "abandoned"
                else ("connected" if item.connected else "disconnected"),
                "attempt_count": item.attempt_count,
                "solve_state": item.solve_state,
                "solve_duration_seconds": (
                    max(0, int((item.solved_at - match.started_at).total_seconds()))
                    if item.solved_at is not None
                    else None
                ),
                "score": item.score,
                "round_score": item.round_score,
                "round_rank": item.round_rank,
                "is_creator": item.is_creator,
            }
            for item in participants
        ],
        "own_attempts": attempts,
        "challenge_setup": setup,
        "result": result,
        "latest_sequence": match.latest_sequence,
        "available_actions": actions,
    }
