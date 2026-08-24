from django.contrib import admin

from apps.matches.models import Match, Participant, RematchProposal, Result, Room, RoomMembership


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "state", "started_at", "deadline", "finished_at")
    readonly_fields = ("id", "rules", "started_at", "deadline", "latest_sequence", "created_at")


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "match", "display_name", "attempt_count", "solve_state")
    readonly_fields = ("id", "match", "guest", "attempt_count", "solve_state", "solved_at")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("match", "outcome", "reason", "secret_revealed", "created_at")
    readonly_fields = (
        "match",
        "outcome",
        "reason",
        "winner_participant_ids",
        "secret_revealed",
        "created_at",
    )


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


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "state", "preset_id", "host", "created_at")
    readonly_fields = ("id", "join_code", "host", "preset_id", "state", "created_at", "updated_at")
    inlines = (RoomMembershipInline,)


@admin.register(RematchProposal)
class RematchProposalAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "source_match", "state", "expires_at", "new_match")
    list_filter = ("state",)
    readonly_fields = (
        "id",
        "room",
        "source_match",
        "requester",
        "state",
        "expires_at",
        "new_match",
        "created_at",
        "updated_at",
    )
