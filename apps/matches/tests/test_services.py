import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Challenge, Match, Participant, Result, Room
from apps.matches.rooms import create_room, join_room, set_ready, start_room
from apps.matches.services import abandon, create_solo, refresh_match_state, submit_guess


def _guest(name: str = "Amir") -> GuestIdentity:
    guest, _ = GuestIdentity.issue(display_name=name, avatar_id="avatar_01")
    return guest


def _command() -> uuid.UUID:
    return uuid.uuid4()


def _friendly() -> tuple[GuestIdentity, GuestIdentity, Match]:
    host, opponent = _guest("Amir"), _guest("Keyvan")
    room, _ = create_room(guest=host, command_id=_command(), preset_id="number_classic_5_v1")
    join_room(guest=opponent, room_id=room.id, command_id=_command())
    set_ready(guest=host, room_id=room.id, command_id=_command(), ready=True)
    set_ready(guest=opponent, room_id=room.id, command_id=_command(), ready=True)
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        match, _ = start_room(guest=host, room_id=room.id, command_id=_command())
    return host, opponent, match


def _solo(secret: str = "12345") -> tuple[GuestIdentity, Match]:
    guest = _guest()
    with patch("apps.games.registry.generate_number_secret", return_value=secret):
        match, created = create_solo(
            guest=guest, command_id=_command(), preset_id="number_classic_5_v1"
        )
    assert created is True
    return guest, match


def _setup_match() -> tuple[GuestIdentity, Match]:
    guest, match = _solo()
    now = timezone.now()
    Match.objects.filter(pk=match.id).update(
        state=Match.State.SETUP, setup_expires_at=now - timedelta(seconds=1)
    )
    match.refresh_from_db()
    return guest, match


@pytest.mark.django_db
def test_create_solo_rejects_unknown_preset() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        create_solo(guest=guest, command_id=_command(), preset_id="bogus")
    assert exc_info.value.status_code == 400
    assert exc_info.value.default_code == "invalid_request"


@pytest.mark.django_db
def test_submit_guess_rejects_unknown_match() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=guest, match_id=uuid.uuid4(), command_id=_command(), guess="12345")
    assert exc_info.value.status_code == 404
    assert exc_info.value.default_code == "match_not_found"


@pytest.mark.django_db
def test_submit_guess_rejects_non_playing_participant() -> None:
    guest, match = _solo()
    participant = match.participants.get(guest=guest)
    Participant.objects.filter(pk=participant.pk).update(
        solve_state=Participant.SolveState.UNSOLVED
    )
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="12345")
    assert exc_info.value.default_code == "match_not_active"
    assert match.state == Match.State.ACTIVE


@pytest.mark.django_db
def test_submit_guess_during_expired_setup_cancels_and_rejects() -> None:
    guest, match = _setup_match()
    now = timezone.now()
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="54321", now=now)
    assert exc_info.value.default_code == "match_not_active"
    match.refresh_from_db()
    assert match.state == Match.State.CANCELLED


@pytest.mark.django_db
def test_submit_guess_rejects_missing_challenge() -> None:
    host, _opponent, match = _friendly()
    Challenge.objects.filter(match=match).delete()
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=host, match_id=match.id, command_id=_command(), guess="54321")
    assert exc_info.value.default_code == "challenge_not_committed"


@pytest.mark.django_db
def test_submit_guess_rejects_attempt_limit_reached() -> None:
    host, _, match = _friendly()
    participant = match.participants.get(guest=host)
    Participant.objects.filter(pk=participant.pk).update(
        attempt_count=12, solve_state=Participant.SolveState.PLAYING
    )
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=host, match_id=match.id, command_id=_command(), guess="54321")
    assert exc_info.value.default_code == "attempt_limit_reached"


@pytest.mark.django_db
def test_friendly_finish_on_deadline_during_submit() -> None:
    host, _, match = _friendly()
    now = timezone.now()
    Match.objects.filter(pk=match.id).update(deadline=now - timedelta(seconds=1))
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=host, match_id=match.id, command_id=_command(), guess="54321", now=now)
    assert exc_info.value.default_code == "deadline_elapsed"
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    assert Result.objects.get(match=match).reason == "deadline"


@pytest.mark.django_db
def test_solo_finish_on_deadline_during_submit() -> None:
    guest, match = _solo()
    now = timezone.now()
    Match.objects.filter(pk=match.id).update(deadline=now - timedelta(seconds=1))
    with pytest.raises(GameAPIError) as exc_info:
        submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="54321", now=now)
    assert exc_info.value.default_code == "deadline_elapsed"


@pytest.mark.django_db
def test_friendly_attempt_limit_finishes_reason_and_resets_room() -> None:
    host, opponent, match = _friendly()
    rules = dict(match.rules)
    rules["attempt_limit"] = 1
    Match.objects.filter(pk=match.id).update(rules=rules)
    host_participant = Participant.objects.get(match=match, guest=host)
    opponent_participant = Participant.objects.get(match=match, guest=opponent)
    Participant.objects.filter(pk=opponent_participant.pk).update(
        solve_state=Participant.SolveState.UNSOLVED
    )
    attempt, _match_after, created = submit_guess(
        guest=host, match_id=match.id, command_id=_command(), guess="54321"
    )
    assert created is True
    assert attempt is not None
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    assert Result.objects.get(match=match).reason == "attempt_limit"
    assert match.room.state == Room.State.READY_CHECK
    assert not match.room.memberships.filter(ready=True).exists()
    assert (
        Participant.objects.get(pk=host_participant.pk).solve_state
        == Participant.SolveState.UNSOLVED
    )


@pytest.mark.django_db
def test_solved_offer_within_grace_draws_but_late_solve_single_winner() -> None:
    host, opponent, match = _friendly()
    base = timezone.now()
    Match.objects.filter(pk=match.id).update(deadline=base + timedelta(minutes=5))
    host_participant = match.participants.get(guest=host)
    opponent_participant = match.participants.get(guest=opponent)
    for item, solved_at in (
        (host_participant, base),
        (opponent_participant, base + timedelta(seconds=1)),
    ):
        Participant.objects.filter(pk=item.pk).update(
            solve_state=Participant.SolveState.SOLVED,
            attempt_count=1,
            solved_at=solved_at,
        )
    Match.objects.filter(pk=match.id).update(
        state=Match.State.FINISHING, finish_due_at=base + timedelta(milliseconds=500)
    )
    refreshed = refresh_match_state(guest=host, match_id=match.id, now=base + timedelta(seconds=2))
    assert refreshed.state == Match.State.FINISHED
    result = Result.objects.get(match=match)
    assert result.outcome == "won"
    assert result.winner_participant_ids == [str(host_participant.id)]


@pytest.mark.django_db
def test_refresh_finishing_past_due_finishes_solved() -> None:
    host, opponent, match = _friendly()
    base = timezone.now()
    Match.objects.filter(pk=match.id).update(
        state=Match.State.FINISHING,
        deadline=base + timedelta(minutes=5),
        finish_due_at=base - timedelta(seconds=1),
    )
    host_participant = match.participants.get(guest=host)
    Participant.objects.filter(pk=host_participant.pk).update(
        solve_state=Participant.SolveState.SOLVED, attempt_count=1, solved_at=base
    )
    opponent_participant = match.participants.get(guest=opponent)
    Participant.objects.filter(pk=opponent_participant.pk).update(
        solve_state=Participant.SolveState.UNSOLVED
    )
    refreshed = refresh_match_state(guest=host, match_id=match.id, now=base + timedelta(seconds=1))
    assert refreshed.state == Match.State.FINISHED
    assert Result.objects.get(match=match).reason == "solved"
    assert Result.objects.get(match=match).winner_participant_ids == [str(host_participant.id)]


@pytest.mark.django_db
def test_refresh_rejects_unknown_match() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        refresh_match_state(guest=guest, match_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_refresh_expired_setup_cancels() -> None:
    guest, match = _setup_match()
    refreshed = refresh_match_state(guest=guest, match_id=match.id)
    assert refreshed.state == Match.State.CANCELLED
    assert refreshed.events.filter(event_type="challenge.setup_cancelled").exists()


@pytest.mark.django_db
def test_abandon_rejects_unknown_match_and_nonparticipant() -> None:
    guest = _guest()
    with pytest.raises(GameAPIError) as exc_info:
        abandon(guest=guest, match_id=uuid.uuid4(), command_id=_command())
    assert exc_info.value.status_code == 404

    _host, _, match = _friendly()
    outsider = _guest("Sara")
    with pytest.raises(GameAPIError) as exc_info:
        abandon(guest=outsider, match_id=match.id, command_id=_command())
    assert exc_info.value.status_code == 403
    assert exc_info.value.default_code == "permission_denied"


@pytest.mark.django_db
def test_abandon_rejects_reused_command_id() -> None:
    guest, match = _solo()
    create_command = match.commands.get(guest=guest)
    with pytest.raises(GameAPIError) as exc_info:
        abandon(guest=guest, match_id=match.id, command_id=create_command.command_id)
    assert exc_info.value.default_code == "idempotency_conflict"


@pytest.mark.django_db
def test_abandon_during_setup_cancels() -> None:
    guest, match = _setup_match()
    abandoned = abandon(guest=guest, match_id=match.id, command_id=_command())
    assert abandoned.state == Match.State.CANCELLED
    assert not Result.objects.filter(match=match).exists()


@pytest.mark.django_db
def test_abandon_friendly_match_hides_secret_and_resets_room() -> None:
    host, _, match = _friendly()
    room_id = match.room_id
    abandoned = abandon(guest=host, match_id=match.id, command_id=_command())
    assert abandoned.state == Match.State.ABANDONED
    result = Result.objects.get(match=match)
    assert result.outcome == "abandoned"
    assert result.secret_revealed is False
    assert result.winner_participant_ids == [str(match.participants.exclude(guest=host).get().id)]
    room = Room.objects.get(pk=room_id)
    assert room.state == Room.State.READY_CHECK
    assert not room.memberships.filter(ready=True).exists()
    assert match.events.filter(event_type="match.finished").exists()


@pytest.mark.django_db
def test_abandon_finished_match_is_rejected() -> None:
    guest, match = _solo()
    submit_guess(guest=guest, match_id=match.id, command_id=_command(), guess="12345")
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    with pytest.raises(GameAPIError) as exc_info:
        abandon(guest=guest, match_id=match.id, command_id=_command())
    assert exc_info.value.default_code == "match_not_active"
