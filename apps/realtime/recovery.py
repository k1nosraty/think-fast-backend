from django.utils import timezone

from apps.matches.challenges import expire_challenge_setup
from apps.matches.models import Match, Participant, RematchProposal
from apps.matches.rematches import expire_rematch_proposal
from apps.matches.services import activate_countdown, refresh_match_state
from apps.realtime.lifecycle import expire_disconnect_grace
from apps.realtime.publisher import publish_pending


def sweep_reliability(*, limit: int = 100) -> dict[str, int]:
    now = timezone.now()
    setup_ids = list(
        Match.objects.filter(state=Match.State.SETUP, setup_expires_at__lte=now).values_list(
            "id", flat=True
        )[:limit]
    )
    expired_setups = sum(expire_challenge_setup(match_id, now=now) for match_id in setup_ids)
    countdown_ids = list(
        Match.objects.filter(state=Match.State.COUNTDOWN, started_at__lte=now).values_list(
            "id", flat=True
        )[:limit]
    )
    for match_id in countdown_ids:
        activate_countdown(match_id, now=now)
    due_matches = list(
        Match.objects.filter(state__in=[Match.State.ACTIVE, Match.State.FINISHING])
        .filter(deadline__lte=now)
        .values_list("id", flat=True)[:limit]
    )
    finishing = list(
        Match.objects.filter(state=Match.State.FINISHING, finish_due_at__lte=now)
        .exclude(id__in=due_matches)
        .values_list("id", flat=True)[:limit]
    )
    for match_id in [*due_matches, *finishing]:
        participant = Participant.objects.filter(match_id=match_id).first()
        if participant is not None:
            refresh_match_state(guest=participant.guest, match_id=match_id, now=now)
    grace_rows = list(
        Participant.objects.filter(
            connected=False, grace_expires_at__lte=now, primary_connection_id__isnull=False
        ).values_list("id", "primary_connection_id")[:limit]
    )
    abandoned = sum(
        expire_disconnect_grace(participant_id=item, connection_id=connection_id, now=now)
        for item, connection_id in grace_rows
        if connection_id is not None
    )
    rematch_ids = list(
        RematchProposal.objects.filter(
            state=RematchProposal.State.PENDING, expires_at__lte=now
        ).values_list("id", flat=True)[:limit]
    )
    expired_rematches = sum(expire_rematch_proposal(item, now=now) for item in rematch_ids)
    delivered, attempted = publish_pending(limit=limit)
    return {
        "challenge_setups_expired": expired_setups,
        "countdowns": len(countdown_ids),
        "matches": len(due_matches) + len(finishing),
        "abandoned": abandoned,
        "rematches_expired": expired_rematches,
        "outbox_attempted": attempted,
        "outbox_delivered": delivered,
    }
