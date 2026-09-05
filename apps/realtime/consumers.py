import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, cast

from channels.db import DatabaseSyncToAsync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.models import MatchEvent, Participant, RoomEvent, RoomMembership
from apps.matches.services import activate_countdown
from apps.realtime.lifecycle import claim_connection, expire_disconnect_grace, release_connection
from apps.realtime.publisher import match_group, room_group
from config.observability import websocket_connected, websocket_disconnected


def database_sync_to_async[T](
    func: Callable[..., T],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Run a DB operation off the single thread-sensitive executor.

    Channels' default ``database_sync_to_async`` is thread-sensitive: every call
    across every consumer is serialized onto one shared executor thread, so a
    burst of WebSocket handshakes runs its per-connection queries one at a time
    regardless of how many pooled PostgreSQL connections are free. That serial
    path — not the pool ceiling — is what throttled the ``sockets_2000`` gate.

    Running these helpers with ``thread_sensitive=False`` lets them execute
    concurrently on asgiref's thread pool. Each call still checks out a pooled
    connection only for its own short transaction and returns it immediately
    (``close_old_connections`` runs on entry and exit), so N held sockets never
    require N checked-out connections. This is safe because every helper below
    is self-contained: none assume a connection or transaction persists across
    calls.
    """

    return cast(
        "Callable[..., Coroutine[Any, Any, T]]",
        DatabaseSyncToAsync(func, thread_sensitive=False),
    )


@database_sync_to_async
def _participant(match_id: uuid.UUID, guest: GuestIdentity) -> Participant | None:
    return Participant.objects.filter(match_id=match_id, guest=guest).first()


@database_sync_to_async
def _event(event_id: str) -> MatchEvent:
    return MatchEvent.objects.select_related("participant").get(pk=event_id)


@database_sync_to_async
def _initial_event_ids(match_id: uuid.UUID) -> list[str]:
    return [
        str(event_id)
        for event_id in MatchEvent.objects.filter(
            match_id=match_id,
            event_type__in=[
                "challenge.setup_started",
                "challenge.committed",
                "challenge.setup_progress",
                "challenge.setup_cancelled",
                "match.countdown_started",
                "match.started",
            ],
        ).values_list("id", flat=True)
    ]


@database_sync_to_async
def _event_ids_after(match_id: uuid.UUID, sequence: int) -> list[str]:
    return [
        str(item)
        for item in MatchEvent.objects.filter(match_id=match_id, sequence__gt=sequence).values_list(
            "id", flat=True
        )
    ]


@database_sync_to_async
def _room_event_ids_after(room_id: uuid.UUID, sequence: int) -> list[str]:
    return [
        str(item)
        for item in RoomEvent.objects.filter(room_id=room_id, sequence__gt=sequence)
        .order_by("sequence")
        .values_list("id", flat=True)
    ]


@database_sync_to_async
def _claim(participant_id: uuid.UUID, connection_id: uuid.UUID, channel_name: str) -> str:
    return claim_connection(
        participant_id=participant_id, connection_id=connection_id, channel_name=channel_name
    )


@database_sync_to_async
def _release(participant_id: uuid.UUID, connection_id: uuid.UUID) -> float | None:
    return release_connection(participant_id=participant_id, connection_id=connection_id)


@database_sync_to_async
def _expire_grace(participant_id: uuid.UUID, connection_id: uuid.UUID) -> bool:
    return expire_disconnect_grace(participant_id=participant_id, connection_id=connection_id)


@database_sync_to_async
def _activate(match_id: uuid.UUID) -> None:
    activate_countdown(match_id)


@database_sync_to_async
def _countdown_delay(match_id: uuid.UUID) -> float | None:
    participant = Participant.objects.select_related("match").filter(match_id=match_id).first()
    if participant is None or participant.match.state != "countdown":
        return None
    return max(0.0, (participant.match.started_at - timezone.now()).total_seconds())


class MatchConsumer(AsyncJsonWebsocketConsumer):
    participant_id: uuid.UUID
    match_id: uuid.UUID
    group_name: str
    countdown_task: asyncio.Task[None]
    grace_task: asyncio.Task[None]
    connection_id: uuid.UUID

    async def connect(self) -> None:
        if not settings.ENABLE_WEBSOCKETS:
            await self.close(code=1013)
            return
        user = self.scope.get("user")
        if not isinstance(user, GuestIdentity):
            await self.close(code=4401)
            return
        self.match_id = uuid.UUID(str(self.scope["url_route"]["kwargs"]["match_id"]))
        participant = await _participant(self.match_id, user)
        if participant is None:
            await self.close(code=4403)
            return
        self.participant_id = participant.id
        self.connection_id = uuid.uuid4()
        self.group_name = match_group(self.match_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        protocols = self.scope.get("subprotocols", [])
        await self.accept(subprotocol="think-fast" if "think-fast" in protocols else None)
        websocket_connected()
        replaced_channel = await _claim(self.participant_id, self.connection_id, self.channel_name)
        if replaced_channel and replaced_channel != self.channel_name:
            await self.channel_layer.send(replaced_channel, {"type": "force.disconnect"})
        for event_id in await _initial_event_ids(self.match_id):
            await self.match_event({"event_id": event_id})
        self.countdown_task = asyncio.create_task(self._activate_when_due())

    async def _activate_when_due(self) -> None:
        delay = await _countdown_delay(self.match_id)
        if delay is None:
            return
        await asyncio.sleep(delay)
        await _activate(self.match_id)

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            websocket_disconnected()
            if hasattr(self, "countdown_task"):
                self.countdown_task.cancel()
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            delay = await _release(self.participant_id, self.connection_id)
            if delay is not None:
                self.grace_task = asyncio.create_task(self._expire_after_grace(delay))

    async def _expire_after_grace(self, delay: float) -> None:
        await asyncio.sleep(delay)
        await _expire_grace(self.participant_id, self.connection_id)

    async def force_disconnect(self, event: dict[str, object]) -> None:
        await self.close(code=4001)

    async def receive_json(self, content: object, **kwargs: object) -> None:
        if not isinstance(content, dict) or content.get("type") != "resync":
            return
        last_sequence = content.get("last_sequence")
        if not isinstance(last_sequence, int) or last_sequence < 0:
            await self.send_json(
                {
                    "type": "system.resync_required",
                    "version": 1,
                    "match_id": str(self.match_id),
                    "sequence": 0,
                    "occurred_at": timezone.now().isoformat().replace("+00:00", "Z"),
                    "visibility": "connection",
                    "payload": {"reason": "invalid_sequence"},
                }
            )
            return
        for event_id in await _event_ids_after(self.match_id, last_sequence):
            await self.match_event({"event_id": event_id})

    async def match_event(self, event: dict[str, str]) -> None:
        stored = await _event(event["event_id"])
        if stored.visibility == "participant" and stored.participant_id != self.participant_id:
            return
        if stored.event_type == "opponent.guessed" and stored.participant_id == self.participant_id:
            return
        await self.send_json(
            {
                "type": stored.event_type,
                "version": 1,
                "match_id": str(stored.match_id),
                "sequence": stored.sequence,
                "occurred_at": stored.occurred_at.isoformat().replace("+00:00", "Z"),
                "visibility": stored.visibility,
                "payload": stored.payload,
            }
        )


@database_sync_to_async
def _room_member(room_id: uuid.UUID, guest: GuestIdentity) -> bool:
    return RoomMembership.objects.filter(room_id=room_id, guest=guest).exists()


@database_sync_to_async
def _room_event(event_id: str) -> RoomEvent:
    return RoomEvent.objects.get(pk=event_id)


class RoomConsumer(AsyncJsonWebsocketConsumer):
    room_id: uuid.UUID
    group_name: str

    async def connect(self) -> None:
        if not settings.ENABLE_WEBSOCKETS:
            await self.close(code=1013)
            return
        user = self.scope.get("user")
        if not isinstance(user, GuestIdentity):
            await self.close(code=4401)
            return
        self.room_id = uuid.UUID(str(self.scope["url_route"]["kwargs"]["room_id"]))
        if not await _room_member(self.room_id, user):
            await self.close(code=4403)
            return
        self.group_name = room_group(self.room_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        protocols = self.scope.get("subprotocols", [])
        await self.accept(subprotocol="think-fast" if "think-fast" in protocols else None)
        websocket_connected()

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            websocket_disconnected()
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: object, **kwargs: object) -> None:
        if not isinstance(content, dict) or content.get("type") != "resync":
            return
        last_sequence = content.get("last_sequence")
        if not isinstance(last_sequence, int) or last_sequence < 0:
            await self.send_json(
                {
                    "type": "system.resync_required",
                    "version": 1,
                    "room_id": str(self.room_id),
                    "sequence": 0,
                    "occurred_at": timezone.now().isoformat().replace("+00:00", "Z"),
                    "visibility": "connection",
                    "payload": {"reason": "invalid_sequence"},
                }
            )
            return
        for event_id in await _room_event_ids_after(self.room_id, last_sequence):
            await self.room_event({"event_id": event_id})

    async def room_event(self, event: dict[str, str]) -> None:
        stored = await _room_event(event["event_id"])
        await self.send_json(
            {
                "type": stored.event_type,
                "version": 1,
                "room_id": str(stored.room_id),
                "sequence": stored.sequence,
                "occurred_at": stored.occurred_at.isoformat().replace("+00:00", "Z"),
                "visibility": "room",
                "payload": stored.payload,
            }
        )
