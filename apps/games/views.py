from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.games.domain import PRESETS


class GameDefinitionListView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "game_read"

    def get(self, request: Request) -> Response:
        definitions = [
            {
                "preset_id": preset_id,
                "display_name_key": f"preset.{preset_id}",
                "rules": rules.snapshot(),
            }
            for preset_id, rules in PRESETS.items()
        ]
        return Response({"contract_version": "v1.0.0-draft.1", "definitions": definitions})
