import uuid

from django.db import models


class AnalyticsEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=40)
    match_id = models.UUIDField(null=True, blank=True)
    room_id = models.UUIDField(null=True, blank=True)
    properties = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["event_type", "occurred_at"])]
        ordering = ["occurred_at", "id"]
