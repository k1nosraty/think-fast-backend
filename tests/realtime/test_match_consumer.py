import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient

from config.asgi import application
from tests.api.test_friendly_flow import active_match, command, guest


@pytest.mark.django_db(transaction=True)
def test_websocket_authorization_and_private_event_projection() -> None:
    async def scenario() -> None:
        host, opponent, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        host_token = host._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        opponent_token = opponent._credentials["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        host_ws = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{match_id}/",
            headers=[
                (b"origin", b"http://testserver"),
                (b"authorization", f"Bearer {host_token}".encode()),
            ],
        )
        opponent_ws = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{match_id}/",
            headers=[(b"origin", b"http://testserver")],
            subprotocols=["think-fast", f"bearer.{opponent_token}"],
        )
        assert (await host_ws.connect())[0] is True
        connected, subprotocol = await opponent_ws.connect()
        assert connected is True
        assert subprotocol == "think-fast"
        assert [
            (await host_ws.receive_json_from(timeout=1))["type"],
            (await host_ws.receive_json_from(timeout=1))["type"],
        ] == ["match.countdown_started", "match.started"]
        assert [
            (await opponent_ws.receive_json_from(timeout=1))["type"],
            (await opponent_ws.receive_json_from(timeout=1))["type"],
        ] == ["match.countdown_started", "match.started"]
        response = await sync_to_async(host.post, thread_sensitive=True)(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
        )
        assert response.status_code == 201
        private = await host_ws.receive_json_from(timeout=1)
        public = await opponent_ws.receive_json_from(timeout=1)
        assert private["type"] == "guess.evaluated"
        assert "feedback" in private["payload"]
        assert public["type"] == "opponent.guessed"
        assert "feedback" not in public["payload"]
        assert "guess" not in public["payload"]
        await host_ws.disconnect()
        await opponent_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_websocket_rejects_anonymous_and_nonparticipant() -> None:
    async def scenario() -> None:
        _, _, started = await sync_to_async(active_match, thread_sensitive=True)()
        match_id = started["match_id"]
        anonymous = WebsocketCommunicator(
            application, f"/ws/v1/matches/{match_id}/", headers=[(b"origin", b"http://testserver")]
        )
        connected, code = await anonymous.connect()
        assert connected is False
        assert code == 4401
        outsider = APIClient()
        guest_response = await sync_to_async(outsider.post, thread_sensitive=True)(
            "/api/v1/guest-sessions/",
            {"display_name": "Outsider", "avatar_id": "avatar_04"},
            format="json",
        )
        token = guest_response.data["access_token"]
        unauthorized = WebsocketCommunicator(
            application,
            f"/ws/v1/matches/{match_id}/",
            headers=[
                (b"origin", b"http://testserver"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
        )
        connected, code = await unauthorized.connect()
        assert connected is False
        assert code == 4403

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_websocket_delivers_join_and_ready_without_private_game_data() -> None:
    async def scenario() -> None:
        host, host_token = await sync_to_async(guest, thread_sensitive=True)("Amir", "avatar_01")
        opponent, _ = await sync_to_async(guest, thread_sensitive=True)("Keyvan", "avatar_02")
        created = await sync_to_async(host.post, thread_sensitive=True)(
            "/api/v1/rooms/", command(preset_id="number_classic_5_v1"), format="json"
        )
        room_id = created.data["room_id"]
        room_ws = WebsocketCommunicator(
            application,
            f"/ws/v1/rooms/{room_id}/",
            headers=[
                (b"origin", b"http://testserver"),
                (b"authorization", f"Bearer {host_token}".encode()),
            ],
        )
        assert (await room_ws.connect())[0] is True
        await sync_to_async(opponent.post, thread_sensitive=True)(
            f"/api/v1/rooms/{room_id}/join/", command(), format="json"
        )
        joined = await room_ws.receive_json_from(timeout=1)
        assert joined["type"] == "room.player_joined"
        assert "guess" not in joined["payload"]
        await sync_to_async(opponent.post, thread_sensitive=True)(
            f"/api/v1/rooms/{room_id}/ready/", command(ready=True), format="json"
        )
        ready_event = await room_ws.receive_json_from(timeout=1)
        assert ready_event["type"] == "room.ready_changed"
        assert ready_event["payload"]["ready"] is True
        await room_ws.disconnect()

    async_to_sync(scenario)()
