from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import GuestIdentity, WSTicket
from apps.accounts.serializers import CreateGuestSerializer
from apps.analytics.throttles import ResilientScopedRateThrottle


class GuestSessionCreateView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ResilientScopedRateThrottle]
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


class GuestSessionRevokeView(APIView):
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "guest_revoke"

    def post(self, request: Request) -> Response:
        guest: GuestIdentity = request.user  # type: ignore[assignment]
        # Idempotent: if already revoked, still succeed
        if guest.revoked_at is None:
            guest.revoked_at = timezone.now()
            guest.save(update_fields=["revoked_at"])

        # Close active WebSocket sessions for this identity
        try:
            channel_layer = get_channel_layer()
            if channel_layer is not None:
                group_name = f"guest.{guest.id}"
                async_to_sync(channel_layer.group_send)(
                    group_name, {"type": "revoke.disconnect"}
                )
        except Exception:  # pragma: no cover - best effort
            pass

        return Response({"revoked": True}, status=status.HTTP_200_OK)


class GuestSessionWSTicketView(APIView):
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "guest_ws_ticket"

    def post(self, request: Request) -> Response:
        guest: GuestIdentity = request.user  # type: ignore[assignment]
        # Issue short-lived single-use ticket
        ticket, token = WSTicket.issue(guest=guest, ttl_seconds=30)
        return Response(
            {
                "ticket": token,
                "expires_at": ticket.expires_at.isoformat().replace("+00:00", "Z"),
            },
            status=status.HTTP_201_CREATED,
        )
