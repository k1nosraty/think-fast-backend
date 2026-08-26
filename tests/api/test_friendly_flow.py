import json
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.matches.models import Challenge, Match, MatchEvent, Participant, Result, RoomMembership
from apps.matches.services import activate_countdown


def guest(name: str, avatar: str) -> tuple[APIClient, str]:
    client = APIClient()
    response = client.post(
        "/api/v1/guest-sessions/", {"display_name": name, "avatar_id": avatar}, format="json"
    )
    token = response.data["access_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, token


def command(**extra: object) -> dict[str, object]:
    return {"command_id": str(uuid.uuid4()), **extra}


def ready(client: APIClient, room_id: str) -> None:
    response = client.post(f"/api/v1/rooms/{room_id}/ready/", command(ready=True), format="json")
    assert response.status_code == 200


def active_match() -> tuple[APIClient, APIClient, dict]:
    host, _ = guest("Amir", "avatar_01")
    opponent, _ = guest("Keyvan", "avatar_02")
    room = host.post("/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json").data
    joined = opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json")
    assert joined.status_code == 200
    ready(host, room["room_id"])
    ready(opponent, room["room_id"])
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        response = host.post(f"/api/v1/rooms/{room['room_id']}/start/", command(), format="json")
    assert response.status_code == 201
    return host, opponent, response.data


@pytest.mark.django_db
def test_room_capacity_ready_host_permission_and_participant_freeze() -> None:
    host, _ = guest("Amir", "avatar_01")
    opponent, _ = guest("Keyvan", "avatar_02")
    third, _ = guest("Sara", "avatar_03")
    created = host.post("/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json")
    assert created.status_code == 201
    room_id = created.data["room_id"]
    assert len(created.data["join_code"]) == 6
    assert (
        opponent.post(f"/api/v1/rooms/{room_id}/join/", command(), format="json").status_code == 200
    )
    full = third.post(f"/api/v1/rooms/{room_id}/join/", command(), format="json")
    assert full.status_code == 409
    assert full.data["code"] == "room_full"
    ready(host, room_id)
    ready(opponent, room_id)
    forbidden = opponent.post(f"/api/v1/rooms/{room_id}/start/", command(), format="json")
    assert forbidden.status_code == 403
    assert forbidden.data["code"] == "not_room_host"
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        started = host.post(f"/api/v1/rooms/{room_id}/start/", command(), format="json")
    assert started.status_code == 201
    assert started.data["rules"]["match_mode"] == "friendly"
    assert len(started.data["participants"]) == 2
    assert Participant.objects.filter(match_id=started.data["match_id"]).count() == 2
    assert Challenge.objects.count() == 1
    late = third.post(f"/api/v1/rooms/{room_id}/join/", command(), format="json")
    assert late.status_code == 409


@pytest.mark.django_db
def test_two_equal_solvers_draw_and_private_histories_never_cross() -> None:
    host, opponent, started = active_match()
    match_id = started["match_id"]
    first = host.post(f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json")
    second = opponent.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
    )
    assert first.status_code == second.status_code == 201
    assert first.data["match_state"] == "finishing"
    assert second.data["match_state"] == "finished"
    assert Result.objects.get(match_id=match_id).outcome == "draw"
    host_snapshot = host.get(f"/api/v1/matches/{match_id}/snapshot/").data
    opponent_snapshot = opponent.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert host_snapshot["result"]["outcome"] == opponent_snapshot["result"]["outcome"] == "draw"
    assert len(host_snapshot["own_attempts"]) == len(opponent_snapshot["own_attempts"]) == 1
    assert host_snapshot["own_attempts"][0]["guess"] == "12345"
    assert "own_attempts" in opponent_snapshot
    assert json.dumps(host_snapshot).count('"guess"') == 1
    assert json.dumps(opponent_snapshot).count('"guess"') == 1
    finished_event = MatchEvent.objects.get(match_id=match_id, event_type="match.finished")
    assert "revealed_secret" not in finished_event.payload
    assert "guess" not in finished_event.payload


@pytest.mark.django_db
def test_host_leave_transfers_ownership_and_resets_ready() -> None:
    host, _ = guest("Amir", "avatar_01")
    opponent, _ = guest("Keyvan", "avatar_02")
    room = host.post("/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json").data
    joined = opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json").data
    ready(opponent, room["room_id"])
    response = host.post(f"/api/v1/rooms/{room['room_id']}/leave/", command(), format="json")
    assert response.status_code == 200
    assert response.data["host_participant_id"] == joined["members"][1]["participant_id"]
    assert response.data["members"][0]["ready"] is False
    assert RoomMembership.objects.count() == 1


@pytest.mark.django_db
def test_cross_match_access_is_denied_without_leakage() -> None:
    host, _, started = active_match()
    outsider, _ = guest("Outsider", "avatar_04")
    response = outsider.get(f"/api/v1/matches/{started['match_id']}/snapshot/")
    assert response.status_code == 403
    assert "12345" not in json.dumps(response.data)
    assert host.get(f"/api/v1/matches/{started['match_id']}/snapshot/").status_code == 200


@pytest.mark.django_db
@override_settings(FRIENDLY_COUNTDOWN_SECONDS=3)
def test_production_countdown_activates_idempotently() -> None:
    host, _ = guest("Amir", "avatar_01")
    opponent, _ = guest("Keyvan", "avatar_02")
    room = host.post("/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json").data
    opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json")
    ready(host, room["room_id"])
    ready(opponent, room["room_id"])
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        started = host.post(f"/api/v1/rooms/{room['room_id']}/start/", command(), format="json")
    match = Match.objects.get(pk=started.data["match_id"])
    assert started.data["state"] == match.state == "countdown"
    assert list(match.events.values_list("event_type", flat=True)) == ["match.countdown_started"]
    activate_countdown(match.id, now=match.started_at)
    activate_countdown(match.id, now=match.started_at)
    match.refresh_from_db()
    assert match.state == "active"
    assert list(match.events.values_list("event_type", flat=True)) == [
        "match.countdown_started",
        "match.started",
    ]
