from django.contrib import admin

from apps.matches.models import Match, Participant, Result


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
