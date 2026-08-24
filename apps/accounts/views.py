from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import GuestIdentity
from apps.accounts.serializers import CreateGuestSerializer


class GuestSessionCreateView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "guest_create"

    def post(self, request: Request) -> Response:
        serializer = CreateGuestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest, token = GuestIdentity.issue(**serializer.validated_data)
        return Response(
            {
                "guest_id": str(guest.id),
                "display_name": guest.display_name,
                "avatar_id": guest.avatar_id,
                "access_token": token,
                "expires_at": guest.expires_at.isoformat().replace("+00:00", "Z"),
            },
            status=status.HTTP_201_CREATED,
        )
