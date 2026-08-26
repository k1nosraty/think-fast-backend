import json
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.matches.challenges import expire_challenge_setup
from apps.matches.models import Challenge, Match, MatchEvent, Result


def guest(name: str, avatar: str) -> APIClient:
    client = APIClient()
    response = client.post(
        "/api/v1/guest-sessions/", {"display_name": name, "avatar_id": avatar}, format="json"
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
    return client


def command(**extra: object) -> dict[str, object]:
    return {"command_id": str(uuid.uuid4()), **extra}


def setup_duel() -> tuple[APIClient, APIClient, dict[str, object]]:
    host = guest("Amir", "avatar_01")
    opponent = guest("Keyvan", "avatar_02")
    room = host.post(
        "/api/v1/rooms/",
        command(preset_id="number_classic_5_v1", challenge_source="players"),
        format="json",
    ).data
    opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json")
    for client in (host, opponent):
        response = client.post(
            f"/api/v1/rooms/{room['room_id']}/ready/", command(ready=True), format="json"
        )
        assert response.status_code == 200
    started = host.post(f"/api/v1/rooms/{room['room_id']}/start/", command(), format="json")
    assert started.status_code == 201
    return host, opponent, started.data


def setup_color_duel() -> tuple[APIClient, APIClient, dict[str, object]]:
    host = guest("Color A", "avatar_01")
    opponent = guest("Color B", "avatar_02")
    room = host.post(
        "/api/v1/rooms/",
        command(preset_id="color_permutation_8_v1", challenge_source="players"),
        format="json",
    ).data
    opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json")
    for client in (host, opponent):
        client.post(f"/api/v1/rooms/{room['room_id']}/ready/", command(ready=True), format="json")
    started = host.post(f"/api/v1/rooms/{room['room_id']}/start/", command(), format="json")
    return host, opponent, started.data


@pytest.mark.django_db
@override_settings(FRIENDLY_COUNTDOWN_SECONDS=0)
def test_symmetric_duel_commit_start_solve_and_viewer_specific_reveal() -> None:
    host, opponent, started = setup_duel()
    match_id = started["match_id"]
    assert started["state"] == "setup"
    assert started["challenge_setup"]["committed_count"] == 0
    assert started["available_actions"] == ["commit_challenge", "leave"]
    assert Challenge.objects.filter(match_id=match_id).count() == 0

    host_command = command(secret="12345")
    first = host.post(f"/api/v1/matches/{match_id}/challenges/", host_command, format="json")
    assert first.status_code == 201
    assert first.data["state"] == "setup"
    assert first.data["challenge_setup"] == {
        "expires_at": first.data["challenge_setup"]["expires_at"],
        "own_challenge_committed": True,
        "committed_count": 1,
        "required_count": 2,
    }
    retry = host.post(f"/api/v1/matches/{match_id}/challenges/", host_command, format="json")
    assert retry.status_code == 200
    immutable = host.post(
        f"/api/v1/matches/{match_id}/challenges/", command(secret="54321"), format="json"
    )
    assert immutable.status_code == 409
    assert immutable.data["code"] == "challenge_already_committed"

    opponent_setup = opponent.get(f"/api/v1/matches/{match_id}/snapshot/")
    assert opponent_setup.status_code == 200
    assert opponent_setup.data["challenge_setup"]["own_challenge_committed"] is False
    assert "12345" not in json.dumps(opponent_setup.data)

    second = opponent.post(
        f"/api/v1/matches/{match_id}/challenges/", command(secret="54321"), format="json"
    )
    assert second.status_code == 201
    assert second.data["state"] == "active"
    challenges = list(
        Challenge.objects.filter(match_id=match_id).select_related("creator", "solver")
    )
    assert len(challenges) == 2
    assert all(item.creator_id != item.solver_id for item in challenges)

    host_solve = host.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
    )
    opponent_solve = opponent.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
    )
    assert host_solve.status_code == opponent_solve.status_code == 201
    host_final = host.get(f"/api/v1/matches/{match_id}/snapshot/").data
    opponent_final = opponent.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert host_final["result"]["revealed_secret"] == "54321"
    assert opponent_final["result"]["revealed_secret"] == "12345"
    assert "12345" not in json.dumps(host_final)
    assert "54321" not in json.dumps(opponent_final)

    public_payloads = json.dumps(
        list(MatchEvent.objects.filter(match_id=match_id).values_list("payload", flat=True))
    )
    assert "12345" not in public_payloads
    assert "54321" not in public_payloads


@pytest.mark.django_db
def test_invalid_secret_outsider_and_guess_during_setup_are_rejected_without_leakage() -> None:
    host, _, started = setup_duel()
    outsider = guest("Sara", "avatar_03")
    match_id = started["match_id"]
    invalid = host.post(
        f"/api/v1/matches/{match_id}/challenges/", command(secret="11111"), format="json"
    )
    assert invalid.status_code == 400
    assert invalid.data["code"] == "repetition_limit_exceeded"
    denied = outsider.post(
        f"/api/v1/matches/{match_id}/challenges/", command(secret="12345"), format="json"
    )
    assert denied.status_code == 403
    assert "12345" not in json.dumps(denied.data)
    early_guess = host.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
    )
    assert early_guess.status_code == 409
    assert early_guess.data["code"] == "match_not_active"
    assert Challenge.objects.filter(match_id=match_id).count() == 0


@pytest.mark.django_db
def test_setup_timeout_cancels_without_result_or_winner_and_is_idempotent() -> None:
    host, _, started = setup_duel()
    match = Match.objects.get(pk=started["match_id"])
    host.post(f"/api/v1/matches/{match.id}/challenges/", command(secret="12345"), format="json")
    assert expire_challenge_setup(match.id, now=match.setup_expires_at) is True
    assert (
        expire_challenge_setup(match.id, now=match.setup_expires_at + timedelta(seconds=1)) is False
    )
    match.refresh_from_db()
    assert match.state == Match.State.CANCELLED
    assert not Result.objects.filter(match=match).exists()
    recovered = host.get(f"/api/v1/matches/{match.id}/snapshot/")
    assert recovered.status_code == 200
    assert recovered.data["state"] == "cancelled"
    assert recovered.data["result"] is None
    assert recovered.data["available_actions"] == []


@pytest.mark.django_db
def test_late_commit_expires_setup_and_never_persists_submitted_secret() -> None:
    host, opponent, started = setup_duel()
    match = Match.objects.get(pk=started["match_id"])
    response = host.post(
        f"/api/v1/matches/{match.id}/challenges/",
        command(secret="12345"),
        format="json",
    )
    assert response.status_code == 201
    match.setup_expires_at = timezone.now() - timedelta(seconds=1)
    match.save(update_fields=["setup_expires_at"])
    response = opponent.post(
        f"/api/v1/matches/{match.id}/challenges/", command(secret="54321"), format="json"
    )
    assert response.status_code == 409
    assert response.data["code"] == "challenge_setup_expired"
    assert Challenge.objects.filter(match=match).count() == 1
    assert not Result.objects.filter(match=match).exists()


@pytest.mark.django_db
@override_settings(FRIENDLY_COUNTDOWN_SECONDS=0)
def test_player_authored_color_permutation_uses_same_safe_setup() -> None:
    host, opponent, started = setup_color_duel()
    match_id = started["match_id"]
    first_secret = ["red", "orange", "yellow", "green", "cyan", "blue", "indigo", "violet"]
    second_secret = list(reversed(first_secret))
    invalid = host.post(
        f"/api/v1/matches/{match_id}/challenges/",
        command(secret=["red"] * 8),
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["code"] == "invalid_permutation"
    assert (
        host.post(
            f"/api/v1/matches/{match_id}/challenges/",
            command(secret=first_secret),
            format="json",
        ).status_code
        == 201
    )
    committed = opponent.post(
        f"/api/v1/matches/{match_id}/challenges/",
        command(secret=second_secret),
        format="json",
    )
    assert committed.status_code == 201
    assert committed.data["state"] == "active"
    solved = host.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess=second_secret), format="json"
    )
    assert solved.status_code == 201
    assert solved.data["feedback"] == {"kind": "exact_count", "exact_count": 8}
