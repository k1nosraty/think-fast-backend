"""Project and operational routes. Product routes begin in T2."""

from django.contrib import admin
from django.urls import path

from apps.accounts.views import GuestSessionCreateView
from apps.games.views import GameDefinitionListView
from apps.matches.views import (
    ChallengeCommitView,
    GuessCreateView,
    LeaveView,
    RematchView,
    RoomByCodeView,
    RoomCreateView,
    RoomDetailView,
    RoomJoinView,
    RoomKickView,
    RoomLeaveView,
    RoomReadyView,
    RoomRulesView,
    RoomStartView,
    SnapshotView,
    SoloMatchCreateView,
)
from config.health import live, ready
from config.metrics import metrics

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
    path("metrics/", metrics, name="metrics"),
    path("api/v1/guest-sessions/", GuestSessionCreateView.as_view(), name="guest-session-create"),
    path("api/v1/game-definitions/", GameDefinitionListView.as_view(), name="game-definition-list"),
    path("api/v1/solo-matches/", SoloMatchCreateView.as_view(), name="solo-match-create"),
    path("api/v1/rooms/", RoomCreateView.as_view(), name="room-create"),
    path("api/v1/rooms/by-code/<str:join_code>/", RoomByCodeView.as_view(), name="room-by-code"),
    path("api/v1/rooms/<uuid:room_id>/", RoomDetailView.as_view(), name="room-detail"),
    path("api/v1/rooms/<uuid:room_id>/join/", RoomJoinView.as_view(), name="room-join"),
    path("api/v1/rooms/<uuid:room_id>/ready/", RoomReadyView.as_view(), name="room-ready"),
    path("api/v1/rooms/<uuid:room_id>/start/", RoomStartView.as_view(), name="room-start"),
    path("api/v1/rooms/<uuid:room_id>/leave/", RoomLeaveView.as_view(), name="room-leave"),
    path("api/v1/rooms/<uuid:room_id>/kick/", RoomKickView.as_view(), name="room-kick"),
    path("api/v1/rooms/<uuid:room_id>/rules/", RoomRulesView.as_view(), name="room-rules"),
    path("api/v1/matches/<uuid:match_id>/guesses/", GuessCreateView.as_view(), name="guess-create"),
    path(
        "api/v1/matches/<uuid:match_id>/challenges/",
        ChallengeCommitView.as_view(),
        name="challenge-commit",
    ),
    path("api/v1/matches/<uuid:match_id>/snapshot/", SnapshotView.as_view(), name="match-snapshot"),
    path("api/v1/matches/<uuid:match_id>/leave/", LeaveView.as_view(), name="match-leave"),
    path(
        "api/v1/matches/<uuid:match_id>/rematch/",
        RematchView.as_view(),
        name="match-rematch",
    ),
]
