import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import (
    CommandRecord,
    Match,
    RematchProposal,
    Room,
    RoomMembership,
)
from apps.matches.rooms import (
    create_room,
    join_room,
    kick_member,
    leave_room,
    room_for_join_code,
    room_snapshot,
    set_ready,
    start_room,
    update_room_rules,
)


def _guest(name: str = "Amir") -> GuestIdentity:
    guest, _ = GuestIdentity.issue(display_name=name, avatar_id="avatar_01")
    return guest


def _command() -> uuid.UUID:
    return uuid.uuid4()


def _ready_room(host: GuestIdentity, opponent: GuestIdentity) -> tuple[Room, uuid.UUID, uuid.UUID]:
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    room.refresh_from_db()
    return room, host, opponent


@pytest.mark.django_db
def test_create_room_is_idempotent_and_conflicts_on_changed_payload() -> None:
    guest = _guest()
    command_id = _command()
    room, created = create_room(guest=guest, command_id=command_id, preset_id="number_classic_5_v1")
    assert created is True
    assert room.state == Room.State.WAITING
    assert len(room.join_code) == 6

    replayed, created = create_room(
        guest=guest, command_id=command_id, preset_id="number_classic_5_v1"
    )
    assert created is False
    assert replayed.id == room.id

    with pytest.raises(GameAPIError) as exc_info:
        create_room(guest=guest, command_id=command_id, preset_id="number_brain_burner_6_v1")
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_create_room_rejects_unknown_preset() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        create_room(guest=guest, command_id=_command(), preset_id="bogus")
    assert exc_info.value.status_code == 400
    assert exc_info.value.default_code == "invalid_request"


@pytest.mark.django_db
@override_settings(ENABLE_PLAYER_AUTHORED_CHALLENGES=False)
def test_create_room_players_source_fails_closed_when_disabled() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        create_room(
            guest=guest,
            command_id=_command(),
            preset_id="number_classic_5_v1",
            challenge_source=Room.ChallengeSource.PLAYERS,
        )
    assert exc_info.value.default_code == "feature_disabled"


@pytest.mark.django_db
@override_settings(ENABLE_MATCH_CREATION=False)
def test_create_room_fails_closed_when_match_creation_disabled() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        create_room(guest=guest, command_id=_command(), preset_id="number_classic_5_v1")
    assert exc_info.value.default_code == "feature_disabled"
    assert exc_info.value.status_code == 503


@pytest.mark.django_db
def test_create_room_retries_colliding_join_codes_then_fails() -> None:
    guest = _guest()
    existing, _ = create_room(
        guest=guest, command_id=_command(), preset_id="number_classic_5_v1"
    )
    colliding = _guest("Keyvan")
    with patch("apps.matches.rooms._join_code", return_value=existing.join_code):
        with pytest.raises(GameAPIError) as exc_info:
            create_room(guest=colliding, command_id=_command(), preset_id="number_classic_5_v1")
    assert exc_info.value.status_code == 503
    assert exc_info.value.default_code == "invalid_request"


@pytest.mark.django_db
def test_join_room_not_found() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        join_room(guest=guest, room_id=uuid.uuid4(), command_id=_command())
    assert exc_info.value.status_code == 404
    assert exc_info.value.default_code == "room_not_found"


@pytest.mark.django_db
def test_join_room_is_idempotent_and_rejects_reused_command() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    command_id = _command()
    _joined_room, created = join_room(guest=opponent, room_id=room.id, command_id=command_id)
    assert created is True
    replayed, created = join_room(guest=opponent, room_id=room.id, command_id=command_id)
    assert created is False
    assert replayed.id == room.id

    other_room, _ = create_room(
        guest=_guest("Sara"), command_id=_command(), preset_id="number_classic_5_v1"
    )
    with pytest.raises(GameAPIError) as exc_info:
        join_room(guest=opponent, room_id=other_room.id, command_id=command_id)
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_join_after_room_is_full_is_rejected() -> None:
    host, first, third = _guest(), _guest(), _guest("Sara")
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=first, room_id=room.id, command_id=_command())
    with pytest.raises(GameAPIError) as exc_info:
        join_room(guest=third, room_id=room.id, command_id=_command())
    assert exc_info.value.default_code == "room_full"


@pytest.mark.django_db
def test_join_room_rejects_once_room_is_locked() -> None:
    host, first = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=first, room_id=room.id, command_id=_command())
    Room.objects.filter(pk=room.id).update(state=Room.State.ACTIVE)
    lockout = _guest("Zeynab")
    with pytest.raises(GameAPIError) as exc_info:
        join_room(guest=lockout, room_id=room.id, command_id=_command())
    assert exc_info.value.default_code == "room_full"


@pytest.mark.django_db
def test_set_ready_validates_membership_state_and_command() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())

    Room.objects.filter(pk=room.id).update(state=Room.State.WAITING)
    with pytest.raises(GameAPIError) as exc_info:
        set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    assert exc_info.value.default_code == "not_ready"

    Room.objects.filter(pk=room.id).update(state=Room.State.READY_CHECK)
    outsider = _guest("Sara")
    with pytest.raises(GameAPIError) as exc_info:
        set_ready(guest=outsider, room_id=room.id, command_id=_command(), ready=True)
    assert exc_info.value.status_code == 403
    assert exc_info.value.default_code == "permission_denied"

    with pytest.raises(GameAPIError) as exc_info:
        set_ready(guest=host, room_id=uuid.uuid4(), command_id=_command(), ready=True)
    assert exc_info.value.status_code == 404

    command_id = _command()
    ready_room = set_ready(guest=host, room_id=room.id, command_id=command_id, ready=True)
    assert ready_room.memberships.get(guest=host).ready is True
    replayed = set_ready(guest=host, room_id=room.id, command_id=command_id, ready=True)
    assert replayed.id == room.id


@pytest.mark.django_db
def test_start_room_requires_host_two_ready_players_and_state() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())

    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    with pytest.raises(GameAPIError) as exc_info:
        start_room(guest=host, room_id=room.id, command_id=_command())
    assert exc_info.value.default_code == "not_ready"

    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    Room.objects.filter(pk=room.id).update(state=Room.State.WAITING)
    with pytest.raises(GameAPIError) as exc_info:
        start_room(guest=host, room_id=room.id, command_id=_command())
    assert exc_info.value.default_code == "not_ready"

    Room.objects.filter(pk=room.id).update(state=Room.State.READY_CHECK)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, created = start_room(guest=host, room_id=room.id, command_id=_command())
    assert created is True
    assert match.state in {Match.State.ACTIVE, Match.State.COUNTDOWN}


@pytest.mark.django_db
def test_start_room_rejects_non_host_and_missing_room() -> None:
    host, opponent = _guest(), _guest()
    room, _, _ = _ready_room(host, opponent)
    with pytest.raises(GameAPIError) as exc_info:
        start_room(guest=opponent, room_id=room.id, command_id=_command())
    assert exc_info.value.status_code == 403
    assert exc_info.value.default_code == "not_room_host"
    with pytest.raises(GameAPIError) as exc_info:
        start_room(guest=host, room_id=uuid.uuid4(), command_id=_command())
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_start_room_idempotent_replay_and_reused_command() -> None:
    host, opponent = _guest(), _guest()
    room, _, _ = _ready_room(host, opponent)
    command_id = _command()
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, created = start_room(guest=host, room_id=room.id, command_id=command_id)
    assert created is True
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        replayed, created = start_room(guest=host, room_id=room.id, command_id=command_id)
    assert created is False
    assert replayed.id == match.id

    other, _ = create_room(guest=opponent, command_id=_command(), preset_id="number_classic_5_v1")
    with pytest.raises(GameAPIError) as exc_info:
        start_room(guest=host, room_id=other.id, command_id=command_id)
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_leave_room_transfers_ownership_and_rejects_active() -> None:
    host, opponent = _guest(), _guest()
    room, _, _ = _ready_room(host, opponent)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        start_room(guest=host, room_id=room.id, command_id=_command())
    with pytest.raises(GameAPIError) as exc_info:
        leave_room(guest=host, room_id=room.id, command_id=_command())
    assert exc_info.value.default_code == "match_not_active"

    idle_room, _, _ = _ready_room(_guest("A"), _guest("B"))
    leave_room(guest=idle_room.host, room_id=idle_room.id, command_id=_command())
    idle_room.refresh_from_db()
    assert idle_room.state == Room.State.WAITING
    remaining = idle_room.memberships.get()
    assert idle_room.host_id == remaining.guest_id
    assert remaining.ready is False


@pytest.mark.django_db
def test_leave_room_closes_when_last_member_leaves() -> None:
    host = _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    result = leave_room(guest=host, room_id=room.id, command_id=_command())
    assert result is None
    room.refresh_from_db()
    assert room.state == Room.State.CLOSED


@pytest.mark.django_db
def test_leave_room_rejects_unknown_room_and_nonmember() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    with pytest.raises(GameAPIError) as exc_info:
        leave_room(guest=host, room_id=uuid.uuid4(), command_id=_command())
    assert exc_info.value.status_code == 404
    with pytest.raises(GameAPIError) as exc_info:
        leave_room(guest=opponent, room_id=room.id, command_id=_command())
    assert exc_info.value.status_code == 403
    assert exc_info.value.default_code == "permission_denied"


@pytest.mark.django_db
def test_leave_room_rejects_reused_command_id() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_command = _command()
    join_room(guest=opponent, room_id=room.id, command_id=join_command)
    with pytest.raises(GameAPIError) as exc_info:
        leave_room(guest=opponent, room_id=room.id, command_id=join_command)
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_room_snapshot_includes_members_and_rematch_state() -> None:
    host, opponent = _guest(), _guest()
    room, _, _ = _ready_room(host, opponent)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())

    proposal = RematchProposal.objects.create(
        room=room,
        source_match=match,
        requester=host,
        expires_at=timezone.now() + timedelta(seconds=30),
    )
    snapshot = room_snapshot(Room.objects.get(pk=room.id), guest=host)
    assert snapshot["room_id"] == str(room.id)
    assert snapshot["join_code"] == room.join_code
    assert snapshot["latest_match_id"] == str(match.id)
    assert snapshot["rematch"]["state"] == "pending"
    host_member = RoomMembership.objects.get(room=room, guest=host)
    assert snapshot["rematch"]["requester_participant_id"] == str(host_member.id)
    assert snapshot["viewer_participant_id"] == str(host_member.id)
    assert len(snapshot["members"]) == 2
    assert all(member["participant_id"] for member in snapshot["members"])

    proposal = RematchProposal.objects.first()
    assert proposal is not None
    assert CommandRecord.objects.filter(room=room).exists()


@pytest.mark.django_db
def test_room_snapshot_viewer_participant_id_is_null_for_non_member() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    outsider = _guest("Sara")
    snapshot = room_snapshot(Room.objects.get(pk=room.id), guest=outsider)
    assert snapshot["viewer_participant_id"] is None
    assert snapshot["host_participant_id"] is not None


@pytest.mark.django_db
def test_room_for_join_code_returns_active_room_only() -> None:
    room, _ = create_room(guest=_guest(), command_id=_command(), preset_id="number_classic_5_v1")
    assert room_for_join_code(room.join_code) is not None
    assert room_for_join_code(room.join_code.lower()) is not None
    Room.objects.filter(pk=room.id).update(state=Room.State.CLOSED)
    assert room_for_join_code(room.join_code) is None
    assert room_for_join_code("ZZZZZZ") is None


@pytest.mark.django_db
def test_kick_member_removes_target_and_resets_ready() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    target = RoomMembership.objects.get(room=room, guest=opponent)
    result = kick_member(guest=host, room_id=room.id, target_participant_id=target.id)
    assert not RoomMembership.objects.filter(room=room, guest=opponent).exists()
    host_member = RoomMembership.objects.get(room=room, guest=host)
    assert host_member.ready is False
    assert result.state == Room.State.WAITING


@pytest.mark.django_db
def test_kick_member_validates_host_target_and_state() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    target = RoomMembership.objects.get(room=room, guest=opponent)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(guest=opponent, room_id=room.id, target_participant_id=target.id)
    assert exc_info.value.default_code == "not_room_host"
    host_member = RoomMembership.objects.get(room=room, guest=host)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(guest=host, room_id=room.id, target_participant_id=host_member.id)
    assert exc_info.value.default_code == "invalid_request"
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(guest=host, room_id=room.id, target_participant_id=uuid.uuid4())
    assert exc_info.value.default_code == "member_not_found"
    Room.objects.filter(pk=room.id).update(state=Room.State.CLOSED)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(guest=host, room_id=room.id, target_participant_id=target.id)
    assert exc_info.value.default_code == "not_ready"
    Room.objects.filter(pk=room.id).update(state=Room.State.READY_CHECK)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(guest=host, room_id=uuid.uuid4(), target_participant_id=target.id)
    assert exc_info.value.default_code == "room_not_found"


@pytest.mark.django_db
def test_update_room_rules_changes_preset_resets_ready_and_state() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    Room.objects.filter(pk=room.id).update(state=Room.State.READY_CHECK)
    room.refresh_from_db()
    result = update_room_rules(
        guest=host, room_id=room.id, preset_id="number_brain_burner_6_v1"
    )
    result.refresh_from_db()
    assert result.preset_id == "number_brain_burner_6_v1"
    assert result.state == Room.State.WAITING
    assert not RoomMembership.objects.filter(room=room, ready=True).exists()


@pytest.mark.django_db
def test_update_room_rules_validates_host_preset_and_state() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    with pytest.raises(GameAPIError) as exc_info:
        update_room_rules(guest=opponent, room_id=room.id, preset_id="number_classic_5_v1")
    assert exc_info.value.default_code == "not_room_host"
    with pytest.raises(GameAPIError) as exc_info:
        update_room_rules(guest=host, room_id=room.id, preset_id="bogus")
    assert exc_info.value.default_code == "invalid_request"
    Room.objects.filter(pk=room.id).update(state=Room.State.CLOSED)
    with pytest.raises(GameAPIError) as exc_info:
        update_room_rules(guest=host, room_id=room.id, preset_id="number_classic_5_v1")
    assert exc_info.value.default_code == "not_ready"