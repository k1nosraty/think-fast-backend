import signal
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.realtime.publisher import publish_pending


class Command(BaseCommand):
    help = "Retry due Room/Match outbox events safely."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100, help="Max rows to attempt per run")
        parser.add_argument(
            "--interval",
            type=float,
            default=getattr(settings, "RELIABILITY_WORKER_INTERVAL_SECONDS", 1.0),
            help="Seconds between runs when --loop is enabled",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously with configurable interval until SIGTERM/SIGINT",
        )

    def handle(self, *args: object, **options: Any) -> None:
        limit = max(1, int(options["limit"]))
        interval = max(0.1, float(options["interval"]))
        loop = bool(options["loop"])

        if not loop:
            delivered, attempted = publish_pending(limit=limit)
            self.stdout.write(f"outbox attempted={attempted} delivered={delivered}")
            return

        self.stdout.write(
            f"publish_outbox looping interval={interval}s limit={limit} "
            "(SIGTERM for clean shutdown)"
        )
        shutdown_requested = False

        def _handle_signal(signum: int, frame: Any) -> None:
            nonlocal shutdown_requested
            shutdown_requested = True
            self.stdout.write(f"publish_outbox received signal {signum}, shutting down...")

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        try:
            while not shutdown_requested:
                start = time.monotonic()
                try:
                    delivered, attempted = publish_pending(limit=limit)
                    self.stdout.write(
                        f"outbox attempted={attempted} delivered={delivered}", ending="\r"
                    )
                except Exception as exc:  # pragma: no cover
                    self.stderr.write(f"publish_outbox failed: {exc}")
                elapsed = time.monotonic() - start
                sleep_for = max(0.0, interval - elapsed)
                slept = 0.0
                while slept < sleep_for and not shutdown_requested:
                    chunk = min(0.2, sleep_for - slept)
                    time.sleep(chunk)
                    slept += chunk
        finally:
            self.stdout.write("\n outbox worker stopped cleanly")
