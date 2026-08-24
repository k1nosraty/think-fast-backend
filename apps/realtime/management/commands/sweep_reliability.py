from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.realtime.recovery import sweep_reliability


class Command(BaseCommand):
    help = "Converge persisted countdowns, deadlines, disconnect grace and outbox delivery."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: Any) -> None:
        result = sweep_reliability(limit=max(1, int(options["limit"])))
        self.stdout.write(" ".join(f"{key}={value}" for key, value in result.items()))
