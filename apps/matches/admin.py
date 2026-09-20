from django.contrib import admin
from django.http import HttpRequest

from apps.matches.models import Match, Participant, RematchProposal, Result, Room, RoomMembership
from config.admin import ReadOnlyProductionAdmin


@admin.register(Match)
class MatchAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "state", "started_at", "deadline", "finished_at")


@admin.register(Participant)
class ParticipantAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "match", "display_name", "attempt_count", "solve_state")


@admin.register(Result)
class ResultAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("match", "outcome", "reason", "secret_revealed", "created_at")


class RoomMembershipInline(admin.TabularInline):  # type: ignore[type-arg]
    model = RoomMembership
    extra = 0
    readonly_fields = (
        "id",
        "guest",
        "display_name",
        "avatar_id",
        "ready",
        "connected",
        "joined_at",
    )
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(Room)
class RoomAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "state", "preset_id", "host", "created_at")
    inlines = (RoomMembershipInline,)


@admin.register(RematchProposal)
class RematchProposalAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "source_match", "state", "expires_at", "new_match")
    list_filter = ("state",)
