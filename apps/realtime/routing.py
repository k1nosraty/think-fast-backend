from django.urls import path

from apps.realtime.consumers import MatchConsumer, RoomConsumer

websocket_urlpatterns = [
    path("ws/v1/rooms/<uuid:room_id>/", RoomConsumer.as_asgi()),
    path("ws/v1/matches/<uuid:match_id>/", MatchConsumer.as_asgi()),
]
