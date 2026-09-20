import signal
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.realtime.recovery import sweep_reliability as _recovery_sweep

# Expose for test patching: apps.realtime.management.commands.sweep_reliability.sweep_reliability
sweep_reliability = _recovery_sweep


class Command(BaseCommand):
    help = "Converge persisted countdowns, deadlines, disconnect grace and outbox delivery."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100, help="Max rows per bucket per sweep")
        parser.add_argument(
            "--interval",
            type=float,
            default=getattr(settings, "RELIABILITY_WORKER_INTERVAL_SECONDS", 1.0),
            help="Seconds between sweeps when --loop is enabled",
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
            # Preserve existing single-run semantics
            result = sweep_reliability(limit=limit)
            self.stdout.write(" ".join(f"{key}={value}" for key, value in result.items()))
            return

        # Continuous mode with clean shutdown
        self.stdout.write(
            f"sweep_reliability looping interval={interval}s limit={limit} "
            "(SIGTERM for clean shutdown)"
        )
        shutdown_requested = False

        def _handle_signal(signum: int, frame: Any) -> None:
            nonlocal shutdown_requested
            shutdown_requested = True
            self.stdout.write(f"sweep_reliability received signal {signum}, shutting down...")

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        try:
            while not shutdown_requested:
                start = time.monotonic()
                try:
                    result = sweep_reliability(limit=limit)
                    self.stdout.write(" ".join(f"{k}={v}" for k, v in result.items()), ending="\r")
                except Exception as exc:  # pragma: no cover
                    self.stderr.write(f"sweep failed: {exc}")
                elapsed = time.monotonic() - start
                sleep_for = max(0.0, interval - elapsed)
                slept = 0.0
                while slept < sleep_for and not shutdown_requested:
                    chunk = min(0.2, sleep_for - slept)
                    time.sleep(chunk)
                    slept += chunk
        finally:
            self.stdout.write("\nreliability worker stopped cleanly")
