import json
import os
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import GuestIdentity
from apps.games.domain import rules_for_mode
from apps.games.secrets import encrypt_secret
from apps.matches.models import Challenge, Match, Participant, Room, RoomMembership

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _join_code(index: int) -> str:
    value = index
    result = []
    for _ in range(6):
        result.append(ALPHABET[value % len(ALPHABET)])
        value //= len(ALPHABET)
    return "".join(reversed(result))


class Command(BaseCommand):
    help = "Create isolated staging-only Friendly fixtures for the k6 capacity harness."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=3000)
        parser.add_argument("--output", required=True)

    @transaction.atomic
    def handle(self, *args: object, **options: Any) -> None:
        if not settings.LOAD_FIXTURES_ENABLED:
            raise CommandError("LOAD_FIXTURES_ENABLED=true is required")
        count = int(options["count"])
        if count < 1 or count > 10_000:
            raise CommandError("--count must be between 1 and 10000")
        output = Path(str(options["output"])).resolve()
        if output.exists():
            raise CommandError("--output must not already exist")
        output.parent.mkdir(parents=True, exist_ok=True)
        rules = rules_for_mode("number_classic_5_v1", "friendly")
        assert rules is not None
        snapshot = rules.snapshot()
        snapshot["preset_id"] = "load_number_classic_5_v1"
        snapshot["match_deadline_seconds"] = 600
        now = timezone.now()
        rows: list[dict[str, str]] = []
        for index in range(count):
            host_token = secrets.token_urlsafe(32)
            opponent_token = secrets.token_urlsafe(32)
            host = GuestIdentity.objects.create(
                display_name=f"Load Host {index}",
                avatar_id="avatar_01",
                token_digest=GuestIdentity.digest_token(host_token),
                expires_at=now + timedelta(hours=1),
            )
            opponent = GuestIdentity.objects.create(
                display_name=f"Load Opponent {index}",
                avatar_id="avatar_02",
                token_digest=GuestIdentity.digest_token(opponent_token),
                expires_at=now + timedelta(hours=1),
            )
            room = Room.objects.create(
                join_code=_join_code(index),
                host=host,
                preset_id="number_classic_5_v1",
                state=Room.State.ACTIVE,
            )
            RoomMembership.objects.bulk_create(
                [
                    RoomMembership(
                        room=room,
                        guest=host,
                        display_name=host.display_name,
                        avatar_id=host.avatar_id,
                        connected=True,
                    ),
                    RoomMembership(
                        room=room,
                        guest=opponent,
                        display_name=opponent.display_name,
                        avatar_id=opponent.avatar_id,
                        connected=True,
                    ),
                ]
            )
            match = Match.objects.create(
                room=room,
                state=Match.State.ACTIVE,
                rules=snapshot,
                started_at=now,
                deadline=now + timedelta(minutes=10),
            )
            Participant.objects.bulk_create(
                [
                    Participant(
                        match=match,
                        guest=host,
                        display_name=host.display_name,
                        avatar_id=host.avatar_id,
                        connected=True,
                    ),
                    Participant(
                        match=match,
                        guest=opponent,
                        display_name=opponent.display_name,
                        avatar_id=opponent.avatar_id,
                        connected=True,
                    ),
                ]
            )
            Challenge.objects.create(match=match, protected_secret=encrypt_secret("12345"))
            rows.append(
                {
                    "match_id": str(match.id),
                    "token": host_token,
                    "guess": "54321",
                }
            )
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(rows, stream, separators=(",", ":"))
        self.stdout.write(f"created={count} output={output}")
