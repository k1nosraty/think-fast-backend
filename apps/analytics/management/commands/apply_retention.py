import hashlib
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.analytics.models import OperationalAuditEvent
from apps.matches.models import Attempt, Challenge, Match, Result


class Command(BaseCommand):
    help = "Apply documented privacy retention rules; dry-run unless --apply is supplied."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--actor", default="scheduled-retention")

    @transaction.atomic
    def handle(self, *args: object, **options: Any) -> None:
        now = timezone.now()
        secret_cutoff = now - timedelta(hours=settings.SECRET_RETENTION_HOURS)
        attempt_cutoff = now - timedelta(days=settings.ATTEMPT_RETENTION_DAYS)
        match_cutoff = now - timedelta(days=settings.MATCH_RETENTION_DAYS)
        guest_cutoff = now - timedelta(days=settings.GUEST_RETENTION_DAYS)
        secret_rows = Challenge.objects.filter(
            match__finished_at__lt=secret_cutoff,
            secret_destroyed_at__isnull=True,
        )
        attempt_rows = Attempt.objects.filter(accepted_at__lt=attempt_cutoff)
        match_rows = Match.objects.filter(finished_at__lt=match_cutoff)
        guest_rows = GuestIdentity.objects.filter(
            last_seen_at__lt=guest_cutoff,
            expires_at__lt=now,
            revoked_at__isnull=True,
        )
        counts = {
            "secrets": secret_rows.count(),
            "attempts": attempt_rows.count(),
            "matches": match_rows.count(),
            "guests": guest_rows.count(),
        }
        if not options["apply"]:
            self.stdout.write("dry_run=true " + " ".join(f"{k}={v}" for k, v in counts.items()))
            return
        actor = str(options["actor"]).strip()
        if not actor or len(actor) > 100:
            raise CommandError("--actor must contain 1 to 100 characters")
        secret_match_ids = list(secret_rows.values_list("match_id", flat=True).distinct())
        secret_rows.update(protected_secret="", secret_destroyed_at=now)
        Result.objects.filter(match_id__in=secret_match_ids).update(secret_revealed=False)
        attempt_rows.delete()
        match_rows.delete()
        for guest in guest_rows.select_for_update():
            guest.display_name = "Deleted Player"
            guest.avatar_id = "avatar_deleted"
            guest.token_digest = hashlib.sha256(f"destroyed:{uuid.uuid4()}".encode()).hexdigest()
            guest.revoked_at = now
            guest.save(update_fields=["display_name", "avatar_id", "token_digest", "revoked_at"])
        OperationalAuditEvent.objects.create(action="retention.applied", actor=actor, counts=counts)
        self.stdout.write("dry_run=false " + " ".join(f"{k}={v}" for k, v in counts.items()))
