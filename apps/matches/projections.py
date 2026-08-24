from datetime import datetime

from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.games.secrets import decrypt_secret
from apps.matches.errors import GameAPIError
from apps.matches.models import Match, Participant


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
    attempts = [
        {
            "attempt_id": str(item.id),
            "ordinal": item.ordinal,
            "guess": item.guess,
            "feedback": item.feedback,
            "accepted_at": iso(item.accepted_at),
            "solved": item.solved,
        }
        for item in participant.attempts.all()
    ]
    result = None
    if hasattr(match, "result"):
        result = {
            "outcome": match.result.outcome,
            "winner_participant_ids": match.result.winner_participant_ids,
            "reason": match.result.reason,
            "secret_revealed": match.result.secret_revealed,
        }
        if match.result.secret_revealed:
            result["revealed_secret"] = decrypt_secret(match.challenge.protected_secret)
    actions = ["submit_guess", "leave"] if match.state == Match.State.ACTIVE else []
    return {
        "contract_version": "v1.0.0-draft.1",
        "match_id": str(match.id),
        "room_id": None,
        "state": match.state,
        "rules": match.rules,
        "server_time": iso(timezone.now()),
        "started_at": iso(match.started_at),
        "deadline": iso(match.deadline),
        "viewer": {
            "participant_id": str(participant.id),
            "display_name": participant.display_name,
            "role": "player",
        },
        "participants": [
            {
                "participant_id": str(participant.id),
                "display_name": participant.display_name,
                "avatar_id": participant.avatar_id,
                "connection_state": "abandoned"
                if participant.solve_state == "abandoned"
                else "connected",
                "attempt_count": participant.attempt_count,
                "solve_state": participant.solve_state,
            }
        ],
        "own_attempts": attempts,
        "result": result,
        "latest_sequence": match.latest_sequence,
        "available_actions": actions,
    }
