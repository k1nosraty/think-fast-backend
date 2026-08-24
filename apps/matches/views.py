import uuid

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import GuestIdentity
from apps.matches.errors import GameAPIError
from apps.matches.models import Room, RoomMembership
from apps.matches.projections import snapshot
from apps.matches.rooms import (
    create_room,
    join_room,
    leave_room,
    room_snapshot,
    set_ready,
    start_room,
)
from apps.matches.serializers import (
    CommandSerializer,
    CreateSoloSerializer,
    GuessSerializer,
    ReadySerializer,
)
from apps.matches.services import abandon, create_solo, refresh_match_state, submit_guess


def authenticated_guest(request: Request) -> GuestIdentity:
    assert isinstance(request.user, GuestIdentity)
    return request.user


class SoloMatchCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "match_create"

    def post(self, request: Request) -> Response:
        serializer = CreateSoloSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match, created = create_solo(
            guest=authenticated_guest(request), **serializer.validated_data
        )
        return Response(
            snapshot(match, authenticated_guest(request)),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class GuessCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "guess"

    def post(self, request: Request, match_id: uuid.UUID) -> Response:
        serializer = GuessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt, match, created = submit_guess(
            guest=authenticated_guest(request), match_id=match_id, **serializer.validated_data
        )
        return Response(
            {
                "command_id": str(attempt.command_id),
                "attempt_id": str(attempt.id),
                "ordinal": attempt.ordinal,
                "feedback": attempt.feedback,
                "solved": attempt.solved,
                "match_state": match.state,
                "latest_sequence": match.latest_sequence,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SnapshotView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "snapshot"

    def get(self, request: Request, match_id: uuid.UUID) -> Response:
        match = refresh_match_state(guest=authenticated_guest(request), match_id=match_id)
        return Response(snapshot(match, authenticated_guest(request)))


class LeaveView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "leave"

    def post(self, request: Request, match_id: uuid.UUID) -> Response:
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match = abandon(
            guest=authenticated_guest(request), match_id=match_id, **serializer.validated_data
        )
        return Response(snapshot(match, authenticated_guest(request)))


class RoomCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "match_create"

    def post(self, request: Request) -> Response:
        serializer = CreateSoloSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room, created = create_room(guest=authenticated_guest(request), **serializer.validated_data)
        return Response(
            room_snapshot(room), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class RoomDetailView(APIView):
    def get(self, request: Request, room_id: uuid.UUID) -> Response:
        room = Room.objects.filter(pk=room_id).first()
        if room is None:
            raise GameAPIError("room_not_found", "Room was not found.", status_code=404)
        if not RoomMembership.objects.filter(
            room=room, guest=authenticated_guest(request)
        ).exists():
            raise GameAPIError("permission_denied", "You are not a room member.", status_code=403)
        return Response(room_snapshot(room))


class RoomJoinView(APIView):
    def post(self, request: Request, room_id: uuid.UUID) -> Response:
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room, _ = join_room(
            guest=authenticated_guest(request), room_id=room_id, **serializer.validated_data
        )
        return Response(room_snapshot(room))


class RoomReadyView(APIView):
    def post(self, request: Request, room_id: uuid.UUID) -> Response:
        serializer = ReadySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = set_ready(
            guest=authenticated_guest(request), room_id=room_id, **serializer.validated_data
        )
        return Response(room_snapshot(room))


class RoomStartView(APIView):
    def post(self, request: Request, room_id: uuid.UUID) -> Response:
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match, created = start_room(
            guest=authenticated_guest(request), room_id=room_id, **serializer.validated_data
        )
        return Response(
            snapshot(match, authenticated_guest(request)),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RoomLeaveView(APIView):
    def post(self, request: Request, room_id: uuid.UUID) -> Response:
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = leave_room(
            guest=authenticated_guest(request), room_id=room_id, **serializer.validated_data
        )
        return Response({"state": "closed"} if room is None else room_snapshot(room))
