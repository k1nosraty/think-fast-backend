import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.matches.models import Attempt, Challenge, Match, Result


def create_guest(client: APIClient, name: str = "Amir") -> tuple[str, str]:
    response = client.post(
        "/api/v1/guest-sessions/", {"display_name": name, "avatar_id": "avatar_01"}, format="json"
    )
    assert response.status_code == 201
    return response.data["guest_id"], response.data["access_token"]


def authorize(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def create_match(client: APIClient, secret: str = "12345") -> dict:
    with patch("apps.games.registry.generate_number_secret", return_value=secret):
        response = client.post(
            "/api/v1/solo-matches/",
            {"command_id": str(uuid.uuid4()), "preset_id": "number_classic_5_v1"},
            format="json",
        )
    assert response.status_code == 201
    return response.data


@pytest.mark.django_db
def test_guest_completes_solo_and_refreshes_terminal_snapshot() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    created = create_match(client)
    assert "secret" not in json.dumps(created).lower()
    match_id = created["match_id"]
    response = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": str(uuid.uuid4()), "guess": "12345"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["solved"] is True
    snapshot = client.get(f"/api/v1/matches/{match_id}/snapshot/")
    assert snapshot.status_code == 200
    assert snapshot.data["state"] == "finished"
    assert snapshot.data["result"]["revealed_secret"] == "12345"
    assert snapshot.data["own_attempts"][0]["guess"] == "12345"


@pytest.mark.django_db
def test_invalid_repeat_and_retry_have_distinct_attempt_semantics() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client, "54321")["match_id"]
    invalid = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": str(uuid.uuid4()), "guess": "11111"},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["code"] == "repetition_limit_exceeded"
    assert Attempt.objects.count() == 0
    first_command = str(uuid.uuid4())
    first = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": first_command, "guess": "12345"},
        format="json",
    )
    retry = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": first_command, "guess": "12345"},
        format="json",
    )
    intentional = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": str(uuid.uuid4()), "guess": "12345"},
        format="json",
    )
    assert (first.status_code, retry.status_code, intentional.status_code) == (201, 200, 201)
    assert first.data == retry.data
    assert Attempt.objects.count() == 2
    assert intentional.data["ordinal"] == 2


@pytest.mark.django_db
def test_idempotency_conflict_is_rejected() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client, "54321")["match_id"]
    command = str(uuid.uuid4())
    client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": command, "guess": "12345"},
        format="json",
    )
    response = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": command, "guess": "12346"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "idempotency_conflict"
    assert Attempt.objects.count() == 1


@pytest.mark.django_db
def test_other_guest_cannot_read_or_guess_match() -> None:
    owner = APIClient()
    _, token = create_guest(owner)
    authorize(owner, token)
    match_id = create_match(owner)["match_id"]
    attacker = APIClient()
    _, attacker_token = create_guest(attacker, "Sara")
    authorize(attacker, attacker_token)
    snapshot = attacker.get(f"/api/v1/matches/{match_id}/snapshot/")
    guess = attacker.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": str(uuid.uuid4()), "guess": "12345"},
        format="json",
    )
    assert snapshot.status_code == guess.status_code == 403
    assert "12345" not in json.dumps(snapshot.data)


@pytest.mark.django_db
def test_expired_deadline_finishes_without_attempt() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client)["match_id"]
    Match.objects.filter(pk=match_id).update(deadline=timezone.now() - timedelta(seconds=1))
    response = client.post(
        f"/api/v1/matches/{match_id}/guesses/",
        {"command_id": str(uuid.uuid4()), "guess": "12345"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "deadline_elapsed"
    assert Attempt.objects.count() == 0
    assert Result.objects.get().reason == "deadline"


@pytest.mark.django_db
def test_snapshot_lazily_finalizes_expired_match() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client)["match_id"]
    Match.objects.filter(pk=match_id).update(deadline=timezone.now() - timedelta(seconds=1))
    response = client.get(f"/api/v1/matches/{match_id}/snapshot/")
    assert response.status_code == 200
    assert response.data["state"] == "finished"
    assert response.data["result"]["reason"] == "deadline"
    assert response.data["result"]["revealed_secret"] == "12345"


@pytest.mark.django_db
def test_abandon_does_not_reveal_secret_and_is_idempotent() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client)["match_id"]
    command = str(uuid.uuid4())
    first = client.post(
        f"/api/v1/matches/{match_id}/leave/", {"command_id": command}, format="json"
    )
    retry = client.post(
        f"/api/v1/matches/{match_id}/leave/", {"command_id": command}, format="json"
    )
    assert first.status_code == retry.status_code == 200
    assert first.data["state"] == "abandoned"
    assert first.data["result"]["secret_revealed"] is False
    assert "revealed_secret" not in first.data["result"]
    assert Challenge.objects.get().protected_secret != "12345"


@pytest.mark.django_db
def test_authentication_is_required() -> None:
    response = APIClient().post(
        "/api/v1/solo-matches/",
        {"command_id": str(uuid.uuid4()), "preset_id": "number_classic_5_v1"},
        format="json",
    )
    assert response.status_code == 401
    assert response.data["code"] == "authentication_required"


@pytest.mark.django_db
def test_game_definitions_match_frozen_presets() -> None:
    response = APIClient().get("/api/v1/game-definitions/")
    assert response.status_code == 200
    assert response.data["contract_version"] == "v1.0.0-draft.1"
    assert {item["preset_id"] for item in response.data["definitions"]} == {
        "number_classic_5_v1",
        "number_brain_burner_6_v1",
        "color_classic_5_v1",
        "color_permutation_8_v1",
    }


@pytest.mark.django_db
def test_create_match_command_is_idempotent_and_conflicts_on_changed_payload() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    command = str(uuid.uuid4())
    payload = {"command_id": command, "preset_id": "number_classic_5_v1"}
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        first = client.post("/api/v1/solo-matches/", payload, format="json")
        retry = client.post("/api/v1/solo-matches/", payload, format="json")
        conflict = client.post(
            "/api/v1/solo-matches/",
            {"command_id": command, "preset_id": "number_brain_burner_6_v1"},
            format="json",
        )
    assert (first.status_code, retry.status_code, conflict.status_code) == (201, 200, 409)
    assert first.data["match_id"] == retry.data["match_id"]
    assert conflict.data["code"] == "idempotency_conflict"
    assert Match.objects.count() == 1


@pytest.mark.django_db
def test_seed_demo_command_creates_playable_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("seed_demo")
    output = capsys.readouterr().out
    assert "access_token=" in output
    assert "match_id=" in output
    assert Match.objects.count() == 1


@pytest.mark.django_db
def test_attempt_limit_finishes_unsolved_and_preserves_full_history() -> None:
    client = APIClient()
    _, token = create_guest(client)
    authorize(client, token)
    match_id = create_match(client, "54321")["match_id"]
    for ordinal in range(1, 13):
        response = client.post(
            f"/api/v1/matches/{match_id}/guesses/",
            {"command_id": str(uuid.uuid4()), "guess": "12345"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["ordinal"] == ordinal
    snapshot = client.get(f"/api/v1/matches/{match_id}/snapshot/")
    assert snapshot.data["state"] == "finished"
    assert snapshot.data["result"]["outcome"] == "unsolved"
    assert snapshot.data["result"]["reason"] == "attempt_limit"
    assert len(snapshot.data["own_attempts"]) == 12
