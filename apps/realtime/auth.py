from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.accounts.models import GuestIdentity, WSTicket


@database_sync_to_async
def _guest_for_token(token: str) -> GuestIdentity | AnonymousUser:
    # First try long-lived guest token
    digest = GuestIdentity.digest_token(token)
    guest = GuestIdentity.objects.filter(token_digest=digest).first()
    if guest is not None and guest.is_active:
        return guest

    # Then try short-lived single-use WS ticket
    ticket_digest = WSTicket.digest_token(token)
    now = timezone.now()
    # Find valid ticket
    ticket = (
        WSTicket.objects.filter(
            token_digest=ticket_digest,
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .select_related("guest")
        .first()
    )
    if ticket is None:
        return AnonymousUser()
    if not ticket.guest.is_active:
        return AnonymousUser()
    # Atomically mark used to prevent replay
    updated = WSTicket.objects.filter(pk=ticket.pk, used_at__isnull=True).update(used_at=now)
    if updated == 0:
        # Already used concurrently
        return AnonymousUser()
    return ticket.guest


class GuestTokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope: dict, receive: object, send: object) -> object:
        headers = dict(scope.get("headers", []))
        token = ""
        authorization = headers.get(b"authorization", b"").decode(errors="ignore")
        if authorization.startswith("Bearer "):
            token = authorization[7:]

        # If no token via Authorization header, try subprotocol ticket
        if not token:
            protocols = list(scope.get("subprotocols", [])) or [
                item.strip()
                for item in headers.get(b"sec-websocket-protocol", b"").decode().split(",")
            ]
            # Preferred: ticket.<token> short-lived single-use
            ticket_proto = next((item for item in protocols if item.startswith("ticket.")), "")
            if ticket_proto:
                token = ticket_proto.removeprefix("ticket.")
            # NOTE: We deliberately do NOT accept bearer.<token> in subprotocol
            # to avoid leaking long-lived bearer tokens in WS metadata.
            # Long-lived tokens must be used via Authorization header or
            # via short-lived ticket obtained over HTTPS.

        scope["user"] = await _guest_for_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
