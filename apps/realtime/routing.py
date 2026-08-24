"""WebSocket routes are intentionally empty until the realtime task."""

from django.urls import URLPattern, URLResolver

websocket_urlpatterns: list[URLPattern | URLResolver] = []
