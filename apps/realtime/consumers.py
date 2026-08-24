import asyncio
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.matches.models import MatchEvent, Participant, RoomEvent, RoomMembership
from apps.matches.services import activate_countdown
from apps.realtime.publisher import match_group, record_event, room_group


@database_sync_to_async
def _participant(match_id: uuid.UUID, guest: GuestIdentity) -> Participant | None:
    return Participant.objects.filter(match_id=match_id, guest=guest).first()


@database_sync_to_async
def _presence(participant_id: uuid.UUID, connected: bool) -> None:
    participant = Participant.objects.select_related("match").get(pk=participant_id)
    if participant.connected == connected:
        return
    participant.connected = connected
    participant.save(update_fields=["connected"])
    record_event(
        match=participant.match,
        event_type="participant.reconnected" if connected else "participant.disconnected",
        visibility="match",
        participant=participant,
        payload={"participant_id": str(participant.id)},
    )


@database_sync_to_async
def _event(event_id: str) -> MatchEvent:
    return MatchEvent.objects.select_related("participant").get(pk=event_id)


@database_sync_to_async
def _initial_event_ids(match_id: uuid.UUID) -> list[str]:
    return [
        str(event_id)
        for event_id in MatchEvent.objects.filter(
            match_id=match_id,
            event_type__in=["match.countdown_started", "match.started"],
        ).values_list("id", flat=True)
    ]


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

    async def connect(self) -> None:
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
        self.group_name = match_group(self.match_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        protocols = self.scope.get("subprotocols", [])
        await self.accept(subprotocol="think-fast" if "think-fast" in protocols else None)
        for event_id in await _initial_event_ids(self.match_id):
            await self.match_event({"event_id": event_id})
        self.countdown_task = asyncio.create_task(self._activate_when_due())
        await _presence(self.participant_id, True)

    async def _activate_when_due(self) -> None:
        delay = await _countdown_delay(self.match_id)
        if delay is None:
            return
        await asyncio.sleep(delay)
        await _activate(self.match_id)

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            if hasattr(self, "countdown_task"):
                self.countdown_task.cancel()
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await _presence(self.participant_id, False)

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

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

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
