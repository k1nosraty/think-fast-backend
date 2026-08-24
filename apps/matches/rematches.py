import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.analytics.service import record_analytics
from apps.matches.errors import GameAPIError
from apps.matches.models import CommandRecord, Match, RematchProposal, Room, RoomMembership
from apps.matches.rooms import _create_friendly_match
from apps.matches.services import fingerprint
from apps.realtime.publisher import record_room_event


def _expire_locked(proposal: RematchProposal, now: datetime) -> bool:
    if proposal.state != RematchProposal.State.PENDING or now < proposal.expires_at:
        return False
    proposal.state = RematchProposal.State.EXPIRED
    proposal.save(update_fields=["state", "updated_at"])
    record_room_event(
        room=proposal.room,
        event_type="rematch.expired",
        payload={"source_match_id": str(proposal.source_match_id)},
    )
    record_analytics(
        "rematch_expired",
        match_id=proposal.source_match_id,
        room_id=proposal.room_id,
        state="expired",
    )
    return True


@transaction.atomic
def expire_rematch_proposal(proposal_id: uuid.UUID, *, now: datetime | None = None) -> bool:
    proposal = (
        RematchProposal.objects.select_for_update()
        .select_related("room")
        .filter(pk=proposal_id)
        .first()
    )
    return False if proposal is None else _expire_locked(proposal, now or timezone.now())


@transaction.atomic
def rematch_command(
    *,
    guest: GuestIdentity,
    match_id: uuid.UUID,
    command_id: uuid.UUID,
    action: str,
) -> tuple[Room, Match | None, bool]:
    match = Match.objects.select_for_update().select_related("room").filter(pk=match_id).first()
    if match is None:
        raise GameAPIError("match_not_found", "Match was not found.", status_code=404)
    if match.room is None:
        raise GameAPIError("invalid_request", "Solo matches do not support rematch.")
    room = Room.objects.select_for_update().get(pk=match.room.pk)
    membership = RoomMembership.objects.filter(room=room, guest=guest).first()
    if membership is None or not match.participants.filter(guest=guest).exists():
        raise GameAPIError("permission_denied", "You are not a match participant.", status_code=403)
    request_hash = fingerprint({"match_id": str(match_id), "action": action})
    prior = CommandRecord.objects.filter(guest=guest, command_id=command_id).first()
    if prior:
        if (
            prior.operation != "rematch"
            or prior.request_fingerprint != request_hash
            or prior.match_id != match.id
        ):
            raise GameAPIError(
                "idempotency_conflict", "Command ID was already used with a different request."
            )
        proposal = RematchProposal.objects.filter(source_match=match).first()
        return room, proposal.new_match if proposal else None, False
    if room.matches.order_by("-created_at").values_list("id", flat=True).first() != match.id:
        raise GameAPIError("match_not_active", "Only the latest Match can be rematched.")
    if match.state not in {Match.State.FINISHED, Match.State.ABANDONED}:
        raise GameAPIError("match_not_active", "Rematch requires a terminal Match.")

    now = timezone.now()
    proposal = (
        RematchProposal.objects.select_for_update()
        .select_related("room")
        .filter(source_match=match)
        .first()
    )
    if proposal is not None:
        _expire_locked(proposal, now)
        proposal.refresh_from_db()

    new_match: Match | None = None
    if action == "decline":
        if proposal is None or proposal.state != RematchProposal.State.PENDING:
            raise GameAPIError("match_not_active", "There is no pending rematch request.")
        proposal.state = RematchProposal.State.DECLINED
        proposal.save(update_fields=["state", "updated_at"])
        record_room_event(
            room=room,
            event_type="rematch.declined",
            payload={"source_match_id": str(match.id), "participant_id": str(membership.id)},
        )
        record_analytics("rematch_declined", match_id=match.id, room_id=room.id, state="declined")
    elif proposal is None or proposal.state in {
        RematchProposal.State.DECLINED,
        RematchProposal.State.EXPIRED,
    }:
        expires_at = now + timedelta(seconds=settings.REMATCH_REQUEST_TTL_SECONDS)
        if proposal is None:
            proposal = RematchProposal.objects.create(
                room=room,
                source_match=match,
                requester=guest,
                expires_at=expires_at,
            )
        else:
            proposal.requester = guest
            proposal.state = RematchProposal.State.PENDING
            proposal.expires_at = expires_at
            proposal.new_match = None
            proposal.save(
                update_fields=["requester", "state", "expires_at", "new_match", "updated_at"]
            )
        record_room_event(
            room=room,
            event_type="rematch.requested",
            payload={
                "source_match_id": str(match.id),
                "participant_id": str(membership.id),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            },
        )
        record_analytics("rematch_requested", match_id=match.id, room_id=room.id, state="pending")
    elif proposal.state == RematchProposal.State.PENDING and proposal.requester_id != guest.id:
        members = list(room.memberships.select_for_update())
        if len(members) != 2:
            raise GameAPIError("room_full", "Exactly two room members are required.")
        new_match = _create_friendly_match(room=room, members=members)
        proposal.state = RematchProposal.State.ACCEPTED
        proposal.new_match = new_match
        proposal.save(update_fields=["state", "new_match", "updated_at"])
        RoomMembership.objects.filter(room=room).update(ready=False)
        record_room_event(
            room=room,
            event_type="rematch.accepted",
            payload={"source_match_id": str(match.id), "new_match_id": str(new_match.id)},
        )
        record_analytics(
            "rematch_accepted",
            match_id=new_match.id,
            room_id=room.id,
            state="accepted",
        )
    elif proposal.state == RematchProposal.State.ACCEPTED:
        new_match = proposal.new_match

    CommandRecord.objects.create(
        guest=guest,
        command_id=command_id,
        operation="rematch",
        request_fingerprint=request_hash,
        room=room,
        match=match,
    )
    return room, new_match, True
