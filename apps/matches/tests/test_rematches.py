import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Match, RematchProposal, Result, Room, RoomMembership
from apps.matches.rematches import expire_rematch_proposal, rematch_command
from apps.matches.rooms import (
    create_room,
    join_room,
    set_ready,
    start_room,
)
from apps.matches.services import create_solo, submit_guess


def _guest(name: str = "Amir") -> GuestIdentity:
    guest, _ = GuestIdentity.issue(display_name=name, avatar_id="avatar_01")
    return guest


def _command() -> uuid.UUID:
    return uuid.uuid4()


def _friendly_match() -> tuple[GuestIdentity, GuestIdentity, Match]:
    host, opponent = _guest("Amir"), _guest("Keyvan")
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())
    return host, opponent, match


def _finished_match() -> tuple[GuestIdentity, GuestIdentity, Match]:
    host, opponent, match = _friendly_match()
    submit_guess(guest=host, match_id=match.id, command_id=_command(), guess="12345")
    submit_guess(guest=opponent, match_id=match.id, command_id=_command(), guess="12345")
    match.refresh_from_db()
    return host, opponent, match


@pytest.mark.django_db
def test_rematch_rejects_solo_match() -> None:
    guest = _guest()
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = create_solo(
            guest=guest, command_id=_command(), preset_id="number_classic_5_v1"
        )
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(guest=guest, match_id=match.id, command_id=_command(), action="request")
    assert exc_info.value.default_code == "invalid_request"


@pytest.mark.django_db
def test_rematch_rejects_non_participant() -> None:
    _, _, match = _finished_match()
    outsider = _guest("Sara")
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(guest=outsider, match_id=match.id, command_id=_command(), action="request")
    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_rematch_rejects_active_match() -> None:
    host, _, match = _friendly_match()
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(guest=host, match_id=match.id, command_id=_command(), action="request")
    assert exc_info.value.default_code == "match_not_active"


@pytest.mark.django_db
def test_rematch_rejects_non_latest_match() -> None:
    host, opponent, match = _finished_match()
    with patch("apps.games.registry.generate_number_secret", return_value="54321"):
        _, _, _ = rematch_command(
            guest=host, match_id=match.id, command_id=_command(), action="request"
        )
        rematch_command(
            guest=opponent, match_id=match.id, command_id=_command(), action="request"
        )
    new_match = Match.objects.filter(room=match.room).order_by("-created_at").first()
    assert new_match is not None and new_match.id != match.id
    new_match.state = Match.State.FINISHED
    new_match.save(update_fields=["state"])
    Result.objects.create(
        match=new_match, outcome="draw", reason="deadline",
        winner_participant_ids=[], secret_revealed=True,
    )
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(guest=host, match_id=match.id, command_id=_command(), action="request")
    assert exc_info.value.default_code == "match_not_active"


@pytest.mark.django_db
def test_decline_rejects_without_pending_proposal() -> None:
    _, _, match = _finished_match()
    opponent = match.participants.exclude(guest=match.room.host).get().guest
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(
            guest=opponent,
            match_id=match.id,
            command_id=_command(),
            action="decline",
        )
    assert exc_info.value.default_code == "match_not_active"


@pytest.mark.django_db
def test_rematch_idempotent_replay_and_conflict() -> None:
    host, _, match = _finished_match()
    command_id = _command()
    room1, _, created = rematch_command(
        guest=host, match_id=match.id, command_id=command_id, action="request"
    )
    assert created is True
    room2, _, created = rematch_command(
        guest=host, match_id=match.id, command_id=command_id, action="request"
    )
    assert created is False
    assert room1.id == room2.id
    with pytest.raises(GameAPIError) as exc_info:
        rematch_command(
            guest=host, match_id=match.id, command_id=command_id, action="decline"
        )
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_decline_then_new_request_creates_proposal() -> None:
    host, opponent, match = _finished_match()
    rematch_command(
        guest=host, match_id=match.id, command_id=_command(), action="request"
    )
    rematch_command(
        guest=opponent, match_id=match.id, command_id=_command(), action="decline"
    )
    _, _, created = rematch_command(
        guest=host, match_id=match.id, command_id=_command(), action="request"
    )
    assert created is True
    proposal = RematchProposal.objects.filter(source_match=match).order_by("-created_at").first()
    assert proposal is not None
    assert proposal.state == RematchProposal.State.PENDING
    assert proposal.requester_id == host.id


@pytest.mark.django_db
def test_expire_rematch_proposal_expires_and_is_idempotent() -> None:
    host, _, match = _finished_match()
    rematch_command(guest=host, match_id=match.id, command_id=_command(), action="request")
    proposal = RematchProposal.objects.get(source_match=match)
    assert expire_rematch_proposal(
        proposal.id, now=proposal.expires_at + timedelta(seconds=1)
    ) is True
    proposal.refresh_from_db()
    assert proposal.state == RematchProposal.State.EXPIRED
    assert expire_rematch_proposal(proposal.id) is False


@pytest.mark.django_db
def test_expire_rematch_proposal_nonexistent_returns_false() -> None:
    assert expire_rematch_proposal(uuid.uuid4()) is False
