from django.contrib import admin

from apps.analytics.models import AnalyticsEvent, OperationalAuditEvent
from config.admin import ReadOnlyProductionAdmin


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("event_type", "match_id", "room_id", "occurred_at")
    list_filter = ("event_type",)


@admin.register(OperationalAuditEvent)
class OperationalAuditEventAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("action", "actor", "occurred_at")
    list_filter = ("action",)
