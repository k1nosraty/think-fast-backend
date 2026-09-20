from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.models import GuestIdentity


class GuestAuthentication(BaseAuthentication):
    keyword = b"Bearer"

    def authenticate(self, request: Request) -> tuple[GuestIdentity, str] | None:
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0] != self.keyword:
            raise AuthenticationFailed("Invalid bearer authorization header.")
        try:
            token = parts[1].decode()
        except UnicodeError as exc:
            raise AuthenticationFailed("Invalid bearer token.") from exc
        guest = GuestIdentity.objects.filter(token_digest=GuestIdentity.digest_token(token)).first()
        if guest is None or not guest.is_active:
            raise AuthenticationFailed("Guest credential is invalid or expired.")
        now = timezone.now()
        if guest.last_seen_at < now - timedelta(hours=24):
            guest.last_seen_at = now
            guest.expires_at = now + timedelta(days=30)
            guest.save(update_fields=["last_seen_at", "expires_at"])
        return guest, token

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"
