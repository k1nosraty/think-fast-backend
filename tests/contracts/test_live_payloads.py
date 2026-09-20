"""Contract conformance for payloads the backend actually produces.

``contracts/fixtures`` holds hand-written illustrative examples, so validating
them cannot prove that the published schemas accept real traffic: a fixture and
a schema can be wrong together and still agree. These tests instead drive the
real HTTP API and validate the generated Snapshot and every stored realtime
event against the published schemas, so a schema that drifts away from the
implementation fails the build instead of silently rejecting valid payloads at
runtime.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.matches.models import MatchEvent, RoomEvent

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_contracts.py"
_SPEC = importlib.util.spec_from_file_location("validate_contracts_live", VALIDATOR_PATH)
assert _SPEC is not None and _SPEC.loader is not None
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)

SNAPSHOT_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "snapshot.schema.json"
EVENT_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "event.schema.json"
SNAPSHOT_SCHEMA = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
EVENT_SCHEMA = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))


def guest(name: str, avatar: str) -> APIClient:
    client = APIClient()
    response = client.post(
        "/api/v1/guest-sessions/", {"display_name": name, "avatar_id": avatar}, format="json"
    )
    assert response.status_code == 201
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
    return client


def command(**extra: object) -> dict[str, object]:
    return {"command_id": str(uuid.uuid4()), **extra}


def assert_snapshot_contract(payload: dict[str, Any], where: str) -> None:
    validator.validate(payload, SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA_PATH, where=where)


def assert_match_events_contract(match_id: str) -> set[str]:
    """Validate stored Match events exactly as the consumer serialises them."""
    seen: set[str] = set()
    for stored in MatchEvent.objects.filter(match_id=match_id).order_by("sequence"):
        envelope = {
            "type": stored.event_type,
            "version": 1,
            "match_id": str(stored.match_id),
            "sequence": stored.sequence,
            "occurred_at": stored.occurred_at.isoformat().replace("+00:00", "Z"),
            "visibility": stored.visibility,
            "payload": stored.payload,
        }
        validator.validate(
            envelope, EVENT_SCHEMA, EVENT_SCHEMA_PATH, where=f"match event {stored.event_type}"
        )
        seen.add(stored.event_type)
    return seen


def assert_room_events_contract(room_id: str) -> set[str]:
    """Validate stored Room events exactly as the room consumer serialises them."""
    seen: set[str] = set()
    for stored in RoomEvent.objects.filter(room_id=room_id).order_by("sequence"):
        envelope = {
            "type": stored.event_type,
            "version": 1,
            "room_id": str(stored.room_id),
            "sequence": stored.sequence,
            "occurred_at": stored.occurred_at.isoformat().replace("+00:00", "Z"),
            "visibility": "room",
            "payload": stored.payload,
        }
        validator.validate(
            envelope, EVENT_SCHEMA, EVENT_SCHEMA_PATH, where=f"room event {stored.event_type}"
        )
        seen.add(stored.event_type)
    return seen


def start_party(clients: list[APIClient], rounds_count: int = 3) -> dict[str, Any]:
    """Create a ready Party Room with the given clients and start its Match."""
    host, *others = clients
    created = host.post(
        "/api/v1/rooms/",
        command(
            preset_id="number_classic_5_v1",
            challenge_source="players",
            room_mode="party",
            rounds_count=rounds_count,
        ),
        format="json",
    )
    assert created.status_code == 201
    room_id = created.data["room_id"]
    for client in others:
        joined = client.post(f"/api/v1/rooms/{room_id}/join/", command(), format="json")
        assert joined.status_code == 200
    for client in clients:
        ready = client.post(f"/api/v1/rooms/{room_id}/ready/", command(ready=True), format="json")
        assert ready.status_code == 200
    started = host.post(f"/api/v1/rooms/{room_id}/start/", command(), format="json")
    assert started.status_code == 201
    return started.data


@pytest.mark.django_db
def test_solo_snapshot_and_events_satisfy_the_published_contract() -> None:
    client = guest("Amir", "avatar_01")
    with patch("apps.games.registry.generate_number_secret", return_value="12345"):
        created = client.post(
            "/api/v1/solo-matches/", command(preset_id="number_classic_5_v1"), format="json"
        )
    assert created.status_code == 201
    assert_snapshot_contract(created.data, "solo active snapshot")
    match_id = created.data["match_id"]

    guessed = client.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
    )
    assert guessed.status_code == 201

    finished = client.get(f"/api/v1/matches/{match_id}/snapshot/")
    assert finished.status_code == 200
    assert_snapshot_contract(finished.data, "solo finished snapshot")
    assert finished.data["result"]["reason"] == "solved"
    assert finished.data["result"]["revealed_secret"] == "12345"
    assert_match_events_contract(match_id)


@pytest.mark.django_db
def test_friendly_duel_snapshot_and_events_satisfy_the_published_contract() -> None:
    host = guest("Amir", "avatar_01")
    opponent = guest("Keyvan", "avatar_02")
    created = host.post(
        "/api/v1/rooms/",
        command(preset_id="number_classic_5_v1", challenge_source="players"),
        format="json",
    )
    assert created.status_code == 201
    room_id = created.data["room_id"]
    assert (
        opponent.post(f"/api/v1/rooms/{room_id}/join/", command(), format="json").status_code == 200
    )
    for client in (host, opponent):
        assert (
            client.post(
                f"/api/v1/rooms/{room_id}/ready/", command(ready=True), format="json"
            ).status_code
            == 200
        )
    started = host.post(f"/api/v1/rooms/{room_id}/start/", command(), format="json")
    assert started.status_code == 201
    assert_snapshot_contract(started.data, "friendly duel start snapshot")
    match_id = started.data["match_id"]

    # A duel Match is created in the player-authored setup phase.
    assert_snapshot_contract(
        host.get(f"/api/v1/matches/{match_id}/snapshot/").data, "friendly duel setup snapshot"
    )
    assert (
        host.post(
            f"/api/v1/matches/{match_id}/challenges/", command(secret="12345"), format="json"
        ).status_code
        == 201
    )
    assert (
        opponent.post(
            f"/api/v1/matches/{match_id}/challenges/", command(secret="54321"), format="json"
        ).status_code
        == 201
    )
    active = host.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert active["state"] == "active"
    assert_snapshot_contract(active, "friendly duel active snapshot")

    assert (
        host.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
        ).status_code
        == 201
    )
    terminal = host.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert_snapshot_contract(terminal, "friendly duel terminal snapshot")
    assert_match_events_contract(match_id)
    assert_room_events_contract(room_id)


@pytest.mark.django_db
def test_party_snapshot_and_events_satisfy_the_published_contract() -> None:
    host = guest("HostPlayer", "avatar_01")
    second = guest("PlayerTwo", "avatar_02")
    third = guest("PlayerThree", "avatar_03")
    started = start_party([host, second, third])
    match_id = started["match_id"]
    room_id = started["room_id"]

    # Round 1 setup: the creator is expected to commit a secret.
    assert_snapshot_contract(started, "party setup snapshot")
    assert started["challenge_setup"]["is_creator"] is True
    assert_snapshot_contract(
        second.get(f"/api/v1/matches/{match_id}/snapshot/").data, "party guesser setup snapshot"
    )

    committed = host.post(
        f"/api/v1/matches/{match_id}/challenges/", command(secret="12345"), format="json"
    )
    assert committed.status_code == 201
    assert_snapshot_contract(committed.data, "party active snapshot")

    # A wrong guess produces participant-private feedback and a public notice.
    wrong = second.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
    )
    assert wrong.status_code == 201
    assert wrong.data["solved"] is False

    # Solving guessers are ranked; the round closes once every guesser solved.
    assert (
        second.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
        ).status_code
        == 201
    )
    assert (
        third.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
        ).status_code
        == 201
    )

    round_finished = second.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert round_finished["round_state"] == "round_finished"
    assert round_finished["result"] is not None
    assert_snapshot_contract(round_finished, "party round finished snapshot")

    advanced = host.post(f"/api/v1/matches/{match_id}/next-round/", command(), format="json")
    assert advanced.status_code == 200
    assert advanced.data["round_number"] == 2
    assert_snapshot_contract(advanced.data, "party next round snapshot")

    emitted = assert_match_events_contract(match_id)
    # These Party events are part of the published enum, so their payloads must
    # stay inside the published contract too.
    assert {
        "creator.selected",
        "round.created",
        "round.started",
        "round.finished",
        "scores.updated",
        "creator.rotated",
        "participant.solved",
    } <= emitted
    assert_room_events_contract(room_id)


@pytest.mark.django_db
def test_party_termination_reason_is_inside_the_published_contract() -> None:
    """A Party Match that drops below the minimum ends with a documented reason.

    ``not_enough_players`` is the reason the backend writes when a Party Match
    can no longer produce placement scoring. It must be part of the published
    vocabulary, otherwise the terminal Snapshot is unparseable for clients.
    """
    host = guest("HostPlayer", "avatar_01")
    second = guest("PlayerTwo", "avatar_02")
    third = guest("PlayerThree", "avatar_03")
    started = start_party([host, second, third])
    match_id = started["match_id"]

    left = third.post(f"/api/v1/matches/{match_id}/leave/", command(), format="json")
    assert left.status_code == 200
    assert left.data["state"] == "abandoned"
    assert left.data["result"]["reason"] == "not_enough_players"
    assert_snapshot_contract(left.data, "party not-enough-players snapshot")
    assert_match_events_contract(match_id)
