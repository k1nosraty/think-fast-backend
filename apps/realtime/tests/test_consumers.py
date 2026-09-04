import asyncio
import uuid

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.matches.models import Match, Participant, Result
from apps.realtime.consumers import MatchConsumer, RoomConsumer
from apps.realtime.publisher import match_group
from config.asgi import application
from tests.api.test_friendly_flow import active_match, command, guest


class _StubChannelLayer:
    async def group_discard(self, group: str, channel: str) -> None:
        pass


def _headers(host: object) -> list[tuple[bytes, bytes]]:
    token = host._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
    return [
        (b"origin", b"http://testserver"),
        (b"authorization", f"Bearer {token}".encode()),
    ]


@pytest.mark.django_db(transaction=True)
@override_settings(ENABLE_WEBSOCKETS=False)
def test_match_consumer_rejects_when_websockets_disabled() -> None:
    async def scenario() -> None:
        _, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        ws = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{started['match_id']}/",
            headers=[(b"origin", b"http://testserver")],
        )
        connected, code = await ws.connect()
        assert connected is False
        assert code == 1013

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_match_consumer_ignores_non_resync_messages() -> None:
    async def scenario() -> None:
        host, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        ws = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{started['match_id']}/",
            headers=_headers(host),
        )
        assert (await ws.connect())[0] is True
        await ws.receive_json_from()
        await ws.receive_json_from()
        await ws.send_json_to({"type": "ping"})
        await ws.send_json_to({"type": "resync", "last_sequence": 5})
        await asyncio.sleep(0.1)
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
@override_settings(FRIENDLY_COUNTDOWN_SECONDS=0.3)
def test_match_consumer_activates_countdown_and_delivers_started() -> None:
    async def scenario() -> None:
        host, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        ws = WebsocketCommunicator(
            application, f"/ws/v1/matches/{match_id}/", headers=_headers(host)
        )
        assert (await ws.connect())[0] is True
        assert (await ws.receive_json_from(timeout=1))["type"] == "match.countdown_started"
        started_event = await ws.receive_json_from(timeout=3)
        assert started_event["type"] == "match.started"
        match = await sync_to_async(lambda: Match.objects.get(pk=match_id), thread_sensitive=True)()
        assert match.state == Match.State.ACTIVE
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_match_consumer_disconnect_is_safe_without_countdown_task() -> None:
    async def scenario() -> None:
        _, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        participant = await sync_to_async(
            lambda: Participant.objects.get(match_id=match_id, guest__display_name="Amir"),
            thread_sensitive=True,
        )()
        consumer = MatchConsumer()
        consumer.match_id = match_id
        consumer.participant_id = participant.id
        consumer.connection_id = uuid.uuid4()
        consumer.group_name = match_group(match_id)
        consumer.channel_layer = _StubChannelLayer()
        consumer.channel_name = "test_channel"
        await consumer.disconnect(None)

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
@override_settings(FRIENDLY_DISCONNECT_GRACE_SECONDS=0.05)
def test_match_consumer_disconnect_starts_grace_expiry() -> None:
    async def scenario() -> None:
        _, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        participant = await sync_to_async(
            lambda: Participant.objects.get(match_id=match_id, guest__display_name="Amir"),
            thread_sensitive=True,
        )()
        connection_id = uuid.uuid4()
        await sync_to_async(
            lambda: Participant.objects.filter(pk=participant.pk).update(
                connected=True, primary_connection_id=connection_id
            ),
            thread_sensitive=True,
        )()
        consumer = MatchConsumer()
        consumer.match_id = match_id
        consumer.participant_id = participant.id
        consumer.connection_id = connection_id
        consumer.group_name = match_group(match_id)
        consumer.channel_layer = _StubChannelLayer()
        consumer.channel_name = "test_channel"
        await consumer.disconnect(None)

        for _ in range(30):
            await asyncio.sleep(0.05)
            state = await sync_to_async(
                lambda: Match.objects.get(pk=match_id).state,
                thread_sensitive=True,
            )()
            if state == Match.State.ABANDONED:
                break
        match = await sync_to_async(lambda: Match.objects.get(pk=match_id), thread_sensitive=True)()
        assert match.state == Match.State.ABANDONED
        result = await sync_to_async(
            lambda: Result.objects.get(match_id=match_id), thread_sensitive=True
        )()
        assert result.secret_revealed is False

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
@override_settings(ENABLE_WEBSOCKETS=False)
def test_room_consumer_rejects_when_websockets_disabled() -> None:
    async def scenario() -> None:
        host, _ = await sync_to_async(guest, thread_sensitive=True)("Amir", "avatar_01")
        created = await sync_to_async(host.post, thread_sensitive=True)(
            "/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json"
        )
        ws = WebsocketCommunicator(
            application,
            f"/ws/v1/rooms/{created.data['room_id']}/",
            headers=_headers(host),
        )
        connected, code = await ws.connect()
        assert connected is False
        assert code == 1013

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_consumer_rejects_anonymous_and_nonmember() -> None:
    async def scenario() -> None:
        host, _ = await sync_to_async(guest, thread_sensitive=True)("Amir", "avatar_01")
        created = await sync_to_async(host.post, thread_sensitive=True)(
            "/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json"
        )
        room_id = created.data["room_id"]
        anonymous = WebsocketCommunicator(
            application, f"/ws/v1/rooms/{room_id}/", headers=[(b"origin", b"http://testserver")]
        )
        connected, code = await anonymous.connect()
        assert connected is False
        assert code == 4401

        outsider, _ = await sync_to_async(guest, thread_sensitive=True)("Sara", "avatar_03")
        ws = WebsocketCommunicator(
            application, f"/ws/v1/rooms/{room_id}/", headers=_headers(outsider)
        )
        connected, code = await ws.connect()
        assert connected is False
        assert code == 4403

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_consumer_resync_replays_authorized_room_events() -> None:
    async def scenario() -> None:
        host, _ = await sync_to_async(guest, thread_sensitive=True)("Amir", "avatar_01")
        opponent, _ = await sync_to_async(guest, thread_sensitive=True)("Keyvan", "avatar_02")
        created = await sync_to_async(host.post, thread_sensitive=True)(
            "/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json"
        )
        room_id = created.data["room_id"]
        await sync_to_async(opponent.post, thread_sensitive=True)(
            f"/api/v1/rooms/{room_id}/join/", command(), format="json"
        )
        await sync_to_async(opponent.post, thread_sensitive=True)(
            f"/api/v1/rooms/{room_id}/ready/", command(ready=True), format="json"
        )
        host_token = host._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        ws = WebsocketCommunicator(
            application,
            f"/ws/v1/rooms/{room_id}/",
            headers=[
                (b"origin", b"http://testserver"),
                (b"authorization", f"Bearer {host_token}".encode()),
            ],
        )
        assert (await ws.connect())[0] is True
        await ws.send_json_to({"type": "ping"})
        await ws.send_json_to({"type": "resync", "last_sequence": 0})
        first = await ws.receive_json_from(timeout=1)
        second = await ws.receive_json_from(timeout=1)
        assert {first["type"], second["type"]} == {
            "room.player_joined",
            "room.ready_changed",
        }
        assert all(item["visibility"] == "room" for item in (first, second))
        await ws.send_json_to({"type": "resync", "last_sequence": -1})
        assert (await ws.receive_json_from(timeout=1))["type"] == "system.resync_required"
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_match_consumer_disconnect_early_returns_without_group() -> None:
    async def scenario() -> None:
        consumer = MatchConsumer()
        consumer.match_id = uuid.uuid4()
        consumer.participant_id = uuid.uuid4()
        consumer.connection_id = uuid.uuid4()
        await consumer.disconnect(None)

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_consumer_disconnect_is_safe_without_group() -> None:
    async def scenario() -> None:
        consumer = RoomConsumer()
        await consumer.disconnect(None)

    async_to_sync(scenario)()
