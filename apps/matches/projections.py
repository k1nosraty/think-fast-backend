from datetime import datetime

from django.utils import timezone

from apps import CONTRACT_VERSION
from apps.accounts.models import GuestIdentity
from apps.games.registry import adapter_for, rules_from_snapshot
from apps.games.secrets import decrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import Challenge, Match, Participant


def iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def snapshot(match: Match, guest: GuestIdentity) -> dict[str, object]:
    participant = (
        Participant.objects.prefetch_related("attempts").filter(match=match, guest=guest).first()
    )
    if participant is None:
        raise GameAPIError(
            "permission_denied", "You are not a participant in this match.", status_code=403
        )
    match.refresh_from_db()
    rules = rules_from_snapshot(match.rules)
    history = rules.history_policy
    is_party = match.room is not None and getattr(match.room, "room_mode", "party") == "party"
    if is_party:
        attempt_rows = list(participant.attempts.filter(round_number=match.round_number))
    else:
        attempt_rows = list(participant.attempts.all())
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
    result = None
    if hasattr(match, "result") and (
        not is_party or match.round_state in {"round_finished", "match_finished"}
    ):
        outcome = match.result.outcome
        if outcome == "won" and str(participant.id) not in match.result.winner_participant_ids:
            outcome = "lost"
        result = {
            "outcome": outcome,
            "winner_participant_ids": match.result.winner_participant_ids,
            "reason": match.result.reason,
            "secret_revealed": match.result.secret_revealed,
        }
        if match.result.secret_revealed:
            challenge = (
                Challenge.objects.filter(
                    match=match, round_number=match.round_number, solver__isnull=True
                ).first()
                or Challenge.objects.filter(match=match, solver=participant).first()
                or Challenge.objects.filter(match=match, solver__isnull=True).first()
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
            own_commit = Challenge.objects.filter(match=match, creator=participant).exists()
            actions = ["leave"] if own_commit else ["commit_challenge", "leave"]
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
            own_commit = Challenge.objects.filter(
                match=match, round_number=match.round_number, creator=participant
            ).exists()
            committed_count = (
                1
                if Challenge.objects.filter(
                    match=match, round_number=match.round_number, committed_at__isnull=False
                ).exists()
                else 0
            )
            setup = {
                "expires_at": iso(match.setup_expires_at),
                "own_challenge_committed": own_commit,
                "committed_count": committed_count,
                "required_count": 1,
                "is_creator": participant.is_creator,
                "creator_participant_id": str(match.creator_id) if match.creator_id else None,
            }
        else:
            own_commit = Challenge.objects.filter(match=match, creator=participant).exists()
            committed_count = Challenge.objects.filter(
                match=match, committed_at__isnull=False
            ).count()
            setup = {
                "expires_at": iso(match.setup_expires_at),
                "own_challenge_committed": own_commit,
                "committed_count": committed_count,
                "required_count": 2,
            }
    participants = list(match.participants.all())
    if result is not None and match.result.winner_participant_ids:
        winner = next(
            (item for item in participants if str(item.id) in match.result.winner_participant_ids),
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
