"""Project and operational routes. Product routes begin in T2."""

from django.contrib import admin
from django.urls import path

from apps.accounts.views import GuestSessionCreateView
from apps.games.views import GameDefinitionListView
from apps.matches.views import GuessCreateView, LeaveView, SnapshotView, SoloMatchCreateView
from config.health import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
    path("api/v1/guest-sessions/", GuestSessionCreateView.as_view(), name="guest-session-create"),
    path("api/v1/game-definitions/", GameDefinitionListView.as_view(), name="game-definition-list"),
    path("api/v1/solo-matches/", SoloMatchCreateView.as_view(), name="solo-match-create"),
    path("api/v1/matches/<uuid:match_id>/guesses/", GuessCreateView.as_view(), name="guess-create"),
    path("api/v1/matches/<uuid:match_id>/snapshot/", SnapshotView.as_view(), name="match-snapshot"),
    path("api/v1/matches/<uuid:match_id>/leave/", LeaveView.as_view(), name="match-leave"),
]
