import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Challenge, Match, Participant, Result
from apps.matches.projections import snapshot
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


def _solo() -> tuple[GuestIdentity, Match]:
    guest = _guest()
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = create_solo(guest=guest, command_id=_command(), preset_id="number_classic_5_v1")
    return guest, match


def _friendly() -> tuple[GuestIdentity, GuestIdentity, Match]:
    host, opponent = _guest("Amir"), _guest("Keyvan")
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())
    return host, opponent, match


@pytest.mark.django_db
def test_snapshot_rejects_non_participant() -> None:
    _, match = _solo()
    outsider = _guest("Sara")
    with pytest.raises(GameAPIError) as exc_info:
        snapshot(match, outsider)
    assert exc_info.value.status_code == 403
    assert exc_info.value.default_code == "permission_denied"


@pytest.mark.django_db
def test_snapshot_for_participant_is_complete_and_private() -> None:
    guest, match = _solo()
    data = snapshot(match, guest)
    assert data["contract_version"] == "v1.0.0-draft.1"
    assert data["state"] == "active"
    assert data["viewer"]["participant_id"] == str(match.participants.get(guest=guest).id)
    assert data["room_id"] is None
    assert data["result"] is None


@pytest.mark.django_db
def test_snapshot_honours_none_history_policy() -> None:
    guest, match = _solo()
    rules = dict(match.rules)
    rules["history_policy"] = {"type": "none"}
    Match.objects.filter(pk=match.id).update(rules=rules)
    submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="12345")
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    data = snapshot(match, guest)
    assert data["result"]["outcome"] == "won"
    assert data["own_attempts"] == []


@pytest.mark.django_db
def test_snapshot_map_won_to_lost_for_non_winner() -> None:
    host, opponent, match = _friendly()
    host_participant = match.participants.get(guest=host)
    opponent_participant = match.participants.get(guest=opponent)
    Result.objects.create(
        match=match,
        outcome="won",
        reason="solved",
        winner_participant_ids=[str(host_participant.id)],
        secret_revealed=True,
    )
    winner_view = snapshot(match, host)
    assert winner_view["result"]["outcome"] == "won"
    loser_view = snapshot(match, opponent)
    assert loser_view["result"]["outcome"] == "lost"
    assert loser_view["result"]["winner_participant_ids"] == [str(host_participant.id)]
    assert opponent_participant is not None


@pytest.mark.django_db
def test_snapshot_hides_revealed_secret_when_destroyed() -> None:
    guest, match = _solo()
    submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="12345")
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    challenge = Challenge.objects.get(match=match)
    Challenge.objects.filter(pk=challenge.pk).update(
        secret_destroyed_at=timezone.now() - timedelta(seconds=1)
    )
    data = snapshot(match, guest)
    assert data["result"]["secret_revealed"] is False
    assert "revealed_secret" not in data["result"]


@pytest.mark.django_db
def test_snapshot_reveals_secret_when_finished() -> None:
    guest, match = _solo()
    submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="12345")
    match.refresh_from_db()
    data = snapshot(match, guest)
    assert data["result"]["secret_revealed"] is True
    assert data["result"]["revealed_secret"] == "12345"


@pytest.mark.django_db
def test_snapshot_reports_setup_actions_for_challenge_commit() -> None:
    guest, match = _solo()
    Match.objects.filter(pk=match.id).update(state=Match.State.SETUP, setup_expires_at=None)
    match.refresh_from_db()
    data = snapshot(match, guest)
    assert data["challenge_setup"] is not None
    assert data["challenge_setup"]["required_count"] == 2
    assert data["challenge_setup"]["own_challenge_committed"] is False
    assert "commit_challenge" in data["available_actions"]
    assert Participant.objects.filter(match=match).count() == 1
