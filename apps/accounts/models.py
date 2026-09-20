import hashlib
import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class GuestIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=20)
    avatar_id = models.CharField(max_length=50)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def digest_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue(cls, *, display_name: str, avatar_id: str) -> tuple["GuestIdentity", str]:
        token = secrets.token_urlsafe(32)
        now = timezone.now()
        guest = cls.objects.create(
            display_name=display_name,
            avatar_id=avatar_id,
            token_digest=cls.digest_token(token),
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
        return guest, token

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class WSTicket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guest = models.ForeignKey(GuestIdentity, on_delete=models.CASCADE, related_name="ws_tickets")
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def digest_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue(cls, *, guest: GuestIdentity, ttl_seconds: int = 30) -> tuple["WSTicket", str]:
        token = secrets.token_urlsafe(32)
        now = timezone.now()
        ticket = cls.objects.create(
            guest=guest,
            token_digest=cls.digest_token(token),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        return ticket, token

    @property
    def is_valid(self) -> bool:
        now = timezone.now()
        return self.used_at is None and self.expires_at > now and self.guest.is_active
