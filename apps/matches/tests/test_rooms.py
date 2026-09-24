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
from apps.matches.rematches import rematch_command
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
    existing, _ = create_room(guest=guest, command_id=_command(), preset_id="number_classic_5_v1")
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
def test_leave_room_resets_all_readiness_in_party() -> None:
    host = _guest("Host")
    p2 = _guest("P2")
    p3 = _guest("P3")
    p4 = _guest("P4")
    room, _ = create_room(
        guest=host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    join_room(guest=p2, room_id=room.id, command_id=_command())
    join_room(guest=p3, room_id=room.id, command_id=_command())
    join_room(guest=p4, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p2, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p3, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p4, room_id=room.id, command_id=_command(), ready=True)
    # All ready
    assert RoomMembership.objects.filter(room=room, ready=True).count() == 4
    leave_room(guest=p4, room_id=room.id, command_id=_command())
    room.refresh_from_db()
    # Remaining members must not retain stale readiness
    assert RoomMembership.objects.filter(room=room, ready=True).count() == 0
    # Party minimum is 3, remaining 3 => READY_CHECK
    assert room.state == Room.State.READY_CHECK
    # Now leave another, remaining 2 < 3 => WAITING
    leave_room(guest=p3, room_id=room.id, command_id=_command())
    room.refresh_from_db()
    assert room.state == Room.State.WAITING


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
    assert snapshot["rules"]["sequence_length"] == 5
    assert snapshot["rules"]["match_mode"] == "friendly"
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
def test_room_snapshot_handles_missing_host_and_requester_left() -> None:
    host = _guest("Host")
    p2 = _guest("P2")
    p3 = _guest("P3")
    room, _ = create_room(
        guest=host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    join_room(guest=p2, room_id=room.id, command_id=_command())
    join_room(guest=p3, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p2, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p3, room_id=room.id, command_id=_command(), ready=True)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())
    # Create rematch proposal from host
    RematchProposal.objects.create(
        room=room,
        source_match=match,
        requester=host,
        expires_at=timezone.now() + timedelta(seconds=30),
    )
    # Host leaves after proposal (simulating requester-left)
    RoomMembership.objects.filter(room=room, guest=host).delete()
    # Transfer host to p2 to avoid completely missing host case for this part
    Room.objects.filter(pk=room.id).update(host=p2)
    room.refresh_from_db()
    # Should not raise StopIteration
    snap = room_snapshot(Room.objects.get(pk=room.id), guest=p2)
    assert snap["rematch"] is not None
    # Requester left => requester_participant_id should be None, not crash
    assert snap["rematch"]["requester_participant_id"] is None
    # Also test missing host: delete all memberships for host id mismatch
    Room.objects.filter(pk=room.id).update(host=host)  # host no longer member
    snap2 = room_snapshot(Room.objects.get(pk=room.id), guest=p2)
    # host_participant_id should fallback, not raise
    assert snap2["host_participant_id"] is not None


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
def test_room_snapshot_publishes_capacity_and_round_policy() -> None:
    host = _guest("Host")
    duel_room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    duel_snap = room_snapshot(Room.objects.get(pk=duel_room.id), guest=host)
    assert duel_snap["minimum_members"] == Room.minimum_members(Room.Mode.DUEL) == 2
    assert duel_snap["maximum_members"] == Room.maximum_members(Room.Mode.DUEL) == 2
    assert duel_snap["allowed_rounds_count"] == Room.allowed_rounds(Room.Mode.DUEL) == [1]

    party_host = _guest("PartyHost")
    party_room, _ = create_room(
        guest=party_host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    party_snap = room_snapshot(Room.objects.get(pk=party_room.id), guest=party_host)
    assert party_snap["minimum_members"] == 3
    assert party_snap["maximum_members"] == 8
    assert party_snap["allowed_rounds_count"] == [3, 5, 7]


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
    result = kick_member(
        guest=host, room_id=room.id, target_participant_id=target.id, command_id=_command()
    )
    assert not RoomMembership.objects.filter(room=room, guest=opponent).exists()
    host_member = RoomMembership.objects.get(room=room, guest=host)
    assert host_member.ready is False
    assert result.state == Room.State.WAITING


@pytest.mark.django_db
def test_kick_member_is_idempotent_and_resets_all_ready_in_party() -> None:
    host = _guest("Host")
    p2 = _guest("P2")
    p3 = _guest("P3")
    room, _ = create_room(
        guest=host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    join_room(guest=p2, room_id=room.id, command_id=_command())
    join_room(guest=p3, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p2, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p3, room_id=room.id, command_id=_command(), ready=True)
    target = RoomMembership.objects.get(room=room, guest=p3)
    cmd_id = _command()
    result = kick_member(
        guest=host, room_id=room.id, target_participant_id=target.id, command_id=cmd_id
    )
    assert result.memberships.count() == 2
    # All remaining ready must be reset
    assert not RoomMembership.objects.filter(room=room, ready=True).exists()
    # Party with 2 remaining < minimum 3 => WAITING (correctly derived)
    assert result.state == Room.State.WAITING
    # Replay same command_id must not repeat mutation and must be idempotent
    replay = kick_member(
        guest=host, room_id=room.id, target_participant_id=target.id, command_id=cmd_id
    )
    assert replay.memberships.count() == 2
    assert replay.id == result.id


@pytest.mark.django_db
def test_kick_member_party_state_derivation() -> None:
    host = _guest("Host")
    p2 = _guest("P2")
    p3 = _guest("P3")
    p4 = _guest("P4")
    room, _ = create_room(
        guest=host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    join_room(guest=p2, room_id=room.id, command_id=_command())
    join_room(guest=p3, room_id=room.id, command_id=_command())
    join_room(guest=p4, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p2, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p3, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p4, room_id=room.id, command_id=_command(), ready=True)
    target = RoomMembership.objects.get(room=room, guest=p4)
    result = kick_member(
        guest=host, room_id=room.id, target_participant_id=target.id, command_id=_command()
    )
    # 3 remaining >= party minimum 3 => READY_CHECK, not blindly WAITING
    assert result.state == Room.State.READY_CHECK
    assert not RoomMembership.objects.filter(room=room, ready=True).exists()


@pytest.mark.django_db
def test_kick_member_validates_host_target_and_state() -> None:
    host, opponent = _guest(), _guest()
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    target = RoomMembership.objects.get(room=room, guest=opponent)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(
            guest=opponent,
            room_id=room.id,
            target_participant_id=target.id,
            command_id=_command(),
        )
    assert exc_info.value.default_code == "not_room_host"
    host_member = RoomMembership.objects.get(room=room, guest=host)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(
            guest=host, room_id=room.id, target_participant_id=host_member.id, command_id=_command()
        )
    assert exc_info.value.default_code == "invalid_request"
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(
            guest=host, room_id=room.id, target_participant_id=uuid.uuid4(), command_id=_command()
        )
    assert exc_info.value.default_code == "member_not_found"
    Room.objects.filter(pk=room.id).update(state=Room.State.CLOSED)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(
            guest=host, room_id=room.id, target_participant_id=target.id, command_id=_command()
        )
    assert exc_info.value.default_code == "not_ready"
    Room.objects.filter(pk=room.id).update(state=Room.State.READY_CHECK)
    with pytest.raises(GameAPIError) as exc_info:
        kick_member(
            guest=host, room_id=uuid.uuid4(), target_participant_id=target.id, command_id=_command()
        )
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
    result = update_room_rules(guest=host, room_id=room.id, preset_id="number_brain_burner_6_v1")
    result.refresh_from_db()
    assert result.preset_id == "number_brain_burner_6_v1"
    assert result.state == Room.State.READY_CHECK
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


@pytest.mark.django_db
def test_party_rematch_supports_3_to_8_players() -> None:
    # A Party rematch must respect the same 3-8 bound as `start_room`.
    host = _guest("Host")
    p2 = _guest("P2")
    p3 = _guest("P3")
    room, _ = create_room(
        guest=host,
        command_id=_command(),
        preset_id="number_classic_5_v1",
        room_mode="party",
        rounds_count=3,
    )
    join_room(guest=p2, room_id=room.id, command_id=_command())
    join_room(guest=p3, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p2, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=p3, room_id=room.id, command_id=_command(), ready=True)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())
    # Simulate finished match
    from apps.matches.models import Match, Result

    Match.objects.filter(pk=match.id).update(state=Match.State.FINISHED)
    Result.objects.create(
        match=match, outcome="won", reason="solved", winner_participant_ids=[], secret_revealed=True
    )
    match.refresh_from_db()
    # First player requests rematch
    _room1, new_match1, created1 = rematch_command(
        guest=host, match_id=match.id, command_id=_command(), action="request"
    )
    assert created1 is True
    assert new_match1 is None
    # Second player accepts - should work for 3 players, not fail with room_full
    room2, new_match2, created2 = rematch_command(
        guest=p2, match_id=match.id, command_id=_command(), action="request"
    )
    assert created2 is True
    assert new_match2 is not None
    assert new_match2.participants.count() == 3
    assert room2.state == Room.State.ACTIVE
