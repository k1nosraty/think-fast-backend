from django.contrib import admin

from apps.analytics.models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("event_type", "match_id", "room_id", "occurred_at")
    list_filter = ("event_type",)
    readonly_fields = ("id", "event_type", "match_id", "room_id", "properties", "occurred_at")
