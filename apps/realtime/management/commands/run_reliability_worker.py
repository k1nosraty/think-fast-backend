import signal
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.realtime.recovery import sweep_reliability


class Command(BaseCommand):
    help = "Continuously run reliability sweeps with configurable interval and clean shutdown."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100, help="Max rows per bucket per sweep")
        parser.add_argument(
            "--interval",
            type=float,
            default=getattr(settings, "RELIABILITY_WORKER_INTERVAL_SECONDS", 1.0),
            help="Seconds between sweeps",
        )

    def handle(self, *args: object, **options: Any) -> None:
        limit = max(1, int(options["limit"]))
        interval = max(0.1, float(options["interval"]))
        self.stdout.write(
            f"reliability worker starting interval={interval}s limit={limit} "
            "(SIGTERM for clean shutdown)"
        )

        # Flag for clean shutdown
        shutdown_requested = False

        def _handle_signal(signum: int, frame: Any) -> None:
            nonlocal shutdown_requested
            shutdown_requested = True
            self.stdout.write(f"reliability worker received signal {signum}, shutting down...")

        # Register handlers for SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        try:
            while not shutdown_requested:
                start = time.monotonic()
                try:
                    result = sweep_reliability(limit=limit)
                    self.stdout.write(
                        " ".join(f"{k}={v}" for k, v in result.items()),
                        ending="\r",
                    )
                except Exception as exc:  # pragma: no cover - defensive, should not happen
                    self.stderr.write(f"reliability sweep failed: {exc}")
                # Sleep remaining interval, but wake up early if shutdown requested
                elapsed = time.monotonic() - start
                sleep_for = max(0.0, interval - elapsed)
                # Sleep in small chunks to respond quickly to shutdown
                slept = 0.0
                while slept < sleep_for and not shutdown_requested:
                    chunk = min(0.2, sleep_for - slept)
                    time.sleep(chunk)
                    slept += chunk
        finally:
            self.stdout.write("\nreliability worker stopped cleanly")
