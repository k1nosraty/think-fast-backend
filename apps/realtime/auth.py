from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import GuestIdentity


@database_sync_to_async
def _guest_for_token(token: str) -> GuestIdentity | AnonymousUser:
    guest = GuestIdentity.objects.filter(token_digest=GuestIdentity.digest_token(token)).first()
    return guest if guest is not None and guest.is_active else AnonymousUser()


class GuestTokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope: dict, receive: object, send: object) -> object:
        headers = dict(scope.get("headers", []))
        token = ""
        authorization = headers.get(b"authorization", b"").decode(errors="ignore")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        if not token:
            protocols = list(scope.get("subprotocols", [])) or [
                item.strip()
                for item in headers.get(b"sec-websocket-protocol", b"").decode().split(",")
            ]
            bearer = next((item for item in protocols if item.startswith("bearer.")), "")
            token = bearer.removeprefix("bearer.")
        scope["user"] = await _guest_for_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
