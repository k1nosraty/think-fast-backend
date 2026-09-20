import json
from unittest.mock import patch

import pytest

from apps.matches.models import Match, MatchEvent, Result
from tests.api.test_friendly_flow import command, guest, ready

CLASSIC_SECRET = ["red", "red", "blue", "green", "yellow"]
CLASSIC_WRONG = ["red", "blue", "red", "slate", "green"]
PERMUTATION_SECRET = ["red", "orange", "yellow", "green", "cyan", "blue", "indigo", "violet"]
PERMUTATION_WRONG = [*PERMUTATION_SECRET[1:], PERMUTATION_SECRET[0]]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("preset_id", "secret", "wrong", "feedback_kind", "history_count"),
    [
        ("color_classic_5_v1", CLASSIC_SECRET, CLASSIC_WRONG, "aggregate", 2),
        (
            "color_permutation_8_v1",
            PERMUTATION_SECRET,
            PERMUTATION_WRONG,
            "exact_count",
            1,
        ),
    ],
)
def test_color_solo_complete_flow(
    preset_id: str,
    secret: list[str],
    wrong: list[str],
    feedback_kind: str,
    history_count: int,
) -> None:
    client, _ = guest("ColorSolo", "avatar_03")
    with patch("apps.games.registry.generate_color_secret", return_value=secret):
        created = client.post("/api/v1/solo-matches/", command(preset_id=preset_id), format="json")
    assert created.status_code == 201
    match_id = created.data["match_id"]
    first = client.post(f"/api/v1/matches/{match_id}/guesses/", command(guess=wrong), format="json")
    solved = client.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess=secret), format="json"
    )
    assert first.status_code == solved.status_code == 201
    assert first.data["feedback"]["kind"] == feedback_kind
    assert solved.data["solved"] is True
    snapshot = client.get(f"/api/v1/matches/{match_id}/snapshot/").data
    assert snapshot["result"]["revealed_secret"] == secret
    assert len(snapshot["own_attempts"]) == history_count
    assert snapshot["own_attempts"][-1]["guess"] == secret


def _friendly_color_match(preset_id: str, secret: list[str]):
    host, _ = guest("ColorHost", "avatar_01")
    opponent, _ = guest("ColorGuest", "avatar_02")
    room = host.post("/api/v1/rooms/", command(preset_id=preset_id), format="json").data
    opponent.post(f"/api/v1/rooms/{room['room_id']}/join/", command(), format="json")
    ready(host, room["room_id"])
    ready(opponent, room["room_id"])
    with patch("apps.games.registry.generate_color_secret", return_value=secret):
        started = host.post(f"/api/v1/rooms/{room['room_id']}/start/", command(), format="json")
    return host, opponent, started.data


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("preset_id", "secret", "wrong", "feedback_kind"),
    [
        ("color_classic_5_v1", CLASSIC_SECRET, CLASSIC_WRONG, "aggregate"),
        (
            "color_permutation_8_v1",
            PERMUTATION_SECRET,
            PERMUTATION_WRONG,
            "exact_count",
        ),
    ],
)
def test_color_friendly_flow_preserves_private_feedback(
    preset_id: str, secret: list[str], wrong: list[str], feedback_kind: str
) -> None:
    host, opponent, started = _friendly_color_match(preset_id, secret)
    match_id = started["match_id"]
    host.post(f"/api/v1/matches/{match_id}/guesses/", command(guess=wrong), format="json")
    opponent.post(f"/api/v1/matches/{match_id}/guesses/", command(guess=secret), format="json")
    host.post(f"/api/v1/matches/{match_id}/guesses/", command(guess=secret), format="json")
    assert Result.objects.get(match_id=match_id).outcome == "won"
    private = MatchEvent.objects.filter(match_id=match_id, event_type="guess.evaluated").first()
    assert private is not None
    assert private.payload["feedback"]["kind"] == feedback_kind
    public_payloads = list(
        MatchEvent.objects.filter(match_id=match_id, visibility="match").values_list(
            "payload", flat=True
        )
    )
    serialized_public = json.dumps(public_payloads)
    assert not any(color_id in serialized_public for color_id in secret)
    assert "feedback" not in serialized_public
    assert Match.objects.get(pk=match_id).rules["game_type"] == "color"
