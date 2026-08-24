from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.realtime.publisher import publish_pending


class Command(BaseCommand):
    help = "Retry due Room/Match outbox events safely."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: Any) -> None:
        delivered, attempted = publish_pending(limit=max(1, int(options["limit"])))
        self.stdout.write(f"outbox attempted={attempted} delivered={delivered}")
