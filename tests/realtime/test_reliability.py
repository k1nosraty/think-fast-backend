import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.utils import timezone

from apps.matches.models import Attempt, Match, MatchEvent, Participant, Result, RoomEvent
from apps.realtime.lifecycle import claim_connection, expire_disconnect_grace, release_connection
from apps.realtime.publisher import publish_match_event, publish_pending, publish_room_event
from apps.realtime.recovery import sweep_reliability
from config.asgi import application
from tests.api.test_friendly_flow import active_match, command


class FailingLayer:
    async def group_send(self, group: str, message: dict[str, object]) -> None:
        raise ConnectionError("redis unavailable")


class RecordingLayer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, object]]] = []

    async def group_send(self, group: str, message: dict[str, object]) -> None:
        self.messages.append((group, message))


@pytest.mark.django_db(transaction=True)
def test_redis_failure_cannot_rollback_attempt_or_winner_and_outbox_recovers() -> None:
    host, opponent, started = active_match()
    match_id = started["match_id"]
    with patch("apps.realtime.publisher.get_channel_layer", return_value=FailingLayer()):
        first = host.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
        )
        second = opponent.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json"
        )
    assert first.status_code == second.status_code == 201
    assert Attempt.objects.filter(participant__match_id=match_id).count() == 2
    assert Result.objects.get(match_id=match_id).outcome == "draw"
    pending = MatchEvent.objects.filter(match_id=match_id, published_at__isnull=True)
    assert pending.exists()
    assert all(item.publish_attempts >= 1 for item in pending)
    pending_count = pending.count()
    pending.update(next_attempt_at=timezone.now() - timedelta(seconds=1))

    healthy = RecordingLayer()
    with patch("apps.realtime.publisher.get_channel_layer", return_value=healthy):
        delivered, attempted = publish_pending(limit=100)
    assert delivered == attempted == pending_count
    assert not MatchEvent.objects.filter(match_id=match_id, published_at__isnull=True).exists()
    serialized = json.dumps(healthy.messages)
    assert "12345" not in serialized


@pytest.mark.django_db(transaction=True)
def test_connection_replacement_closes_old_socket_without_false_disconnect() -> None:
    async def scenario() -> None:
        host, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        token = host._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        path = f"/ws/v1/matches/{started['match_id']}/"
        headers = [
            (b"origin", b"http://testserver"),
            (b"authorization", f"Bearer {token}".encode()),
        ]
        old = WebsocketCommunicator(application, path, headers=headers)
        new = WebsocketCommunicator(application, path, headers=headers)
        assert (await old.connect())[0] is True
        await old.receive_json_from()
        await old.receive_json_from()
        assert (await new.connect())[0] is True
        await new.receive_json_from()
        await new.receive_json_from()
        assert await old.receive_output(timeout=1) == {"type": "websocket.close", "code": 4001}
        participant_id = await sync_to_async(
            lambda: (
                Participant.objects.get(match_id=started["match_id"], guest__display_name="Amir").id
            ),
            thread_sensitive=True,
        )()
        connected = await sync_to_async(
            lambda: Participant.objects.get(pk=participant_id).connected, thread_sensitive=True
        )()
        assert connected is True
        await new.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_reconnect_within_grace_survives_but_expiry_abandons_without_secret() -> None:
    _, _, started = active_match()
    match = Match.objects.get(pk=started["match_id"])
    participant = match.participants.order_by("id").first()
    assert participant is not None
    now = timezone.now()
    first_connection = uuid.uuid4()
    claim_connection(
        participant_id=participant.id, connection_id=first_connection, channel_name="old"
    )
    release_connection(participant_id=participant.id, connection_id=first_connection, now=now)
    replacement = uuid.uuid4()
    claim_connection(
        participant_id=participant.id, connection_id=replacement, channel_name="replacement"
    )
    assert not expire_disconnect_grace(
        participant_id=participant.id,
        connection_id=first_connection,
        now=now + timedelta(minutes=1),
    )
    match.refresh_from_db()
    assert match.state == Match.State.ACTIVE

    release_connection(participant_id=participant.id, connection_id=replacement, now=now)
    assert expire_disconnect_grace(
        participant_id=participant.id,
        connection_id=replacement,
        now=now + timedelta(minutes=1),
    )
    match.refresh_from_db()
    assert match.state == Match.State.ABANDONED
    result = Result.objects.get(match=match)
    assert result.secret_revealed is False
    assert "12345" not in json.dumps(
        MatchEvent.objects.get(match=match, event_type="match.finished").payload
    )


@pytest.mark.django_db(transaction=True)
def test_match_resync_replays_ordered_authorized_gap_only() -> None:
    async def scenario() -> None:
        host, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        token = host._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        response = await sync_to_async(host.post, thread_sensitive=True)(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
        )
        assert response.status_code == 201
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{match_id}/",
            headers=[
                (b"origin", b"http://testserver"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
        )
        assert (await socket.connect())[0] is True
        await socket.receive_json_from()
        await socket.receive_json_from()
        await socket.send_json_to({"type": "resync", "last_sequence": 2})
        replayed = [await socket.receive_json_from()]
        assert [item["sequence"] for item in replayed] == sorted(
            item["sequence"] for item in replayed
        )
        assert [item["type"] for item in replayed] == ["guess.evaluated"]
        assert "feedback" in replayed[0]["payload"]
        await socket.send_json_to({"type": "resync", "last_sequence": -1})
        assert (await socket.receive_json_from())["type"] == "system.resync_required"
        await socket.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_publish_is_idempotent_and_missing_layer_marks_outbox_retry() -> None:
    _, _, started = active_match()
    match_event = (
        MatchEvent.objects.filter(match_id=started["match_id"])
        .order_by("sequence")
        .first()
    )
    room_event = RoomEvent.objects.order_by("sequence").first()
    assert match_event is not None and room_event is not None

    assert publish_match_event(match_event.id) is True
    assert publish_match_event(match_event.id) is True
    assert publish_room_event(room_event.id) is True
    assert publish_room_event(room_event.id) is True
    match_event.refresh_from_db()
    room_event.refresh_from_db()
    assert match_event.published_at is not None
    assert room_event.published_at is not None

    MatchEvent.objects.filter(match_id=started["match_id"]).update(
        published_at=None, publish_attempts=0, next_attempt_at=None, last_error=""
    )
    with patch("apps.realtime.publisher.get_channel_layer", return_value=None):
        assert publish_match_event(match_event.id) is False
    match_event.refresh_from_db()
    assert match_event.publish_attempts >= 1
    assert match_event.last_error == "RuntimeError"
    assert match_event.next_attempt_at is not None

    RoomEvent.objects.update(
        published_at=None, publish_attempts=0, next_attempt_at=None, last_error=""
    )
    with patch("apps.realtime.publisher.get_channel_layer", return_value=FailingLayer()):
        assert publish_room_event(room_event.id) is False
    room_event.refresh_from_db()
    assert room_event.publish_attempts >= 1
    assert room_event.last_error == "ConnectionError"

    RoomEvent.objects.update(
        published_at=None, publish_attempts=0, next_attempt_at=None, last_error=""
    )
    with patch("apps.realtime.publisher.get_channel_layer", return_value=None):
        assert publish_room_event(room_event.id) is False
    room_event.refresh_from_db()
    assert room_event.last_error == "RuntimeError"


@pytest.mark.django_db(transaction=True)
def test_restart_sweeper_converges_persisted_deadline_and_pending_delivery() -> None:
    _, _, started = active_match()
    match = Match.objects.get(pk=started["match_id"])
    match.deadline = timezone.now() - timedelta(seconds=1)
    match.save(update_fields=["deadline"])
    MatchEvent.objects.filter(match=match).update(
        published_at=None, next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    layer = RecordingLayer()
    with patch("apps.realtime.publisher.get_channel_layer", return_value=layer):
        outcome = sweep_reliability(limit=100)
    match.refresh_from_db()
    assert match.state == Match.State.FINISHED
    assert Result.objects.get(match=match).reason == "deadline"
    assert outcome["matches"] == 1
    assert outcome["outbox_delivered"] == outcome["outbox_attempted"]
    assert not MatchEvent.objects.filter(match=match, published_at__isnull=True).exists()
