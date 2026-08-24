import csv
import io
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Count
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent


class Command(BaseCommand):
    help = "Export privacy-safe aggregate playtest analytics as JSON or CSV."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--format", choices=["json", "csv"], default="json")
        parser.add_argument("--since-days", type=int, default=30)
        parser.add_argument("--output", type=Path)

    def handle(self, *args: object, **options: Any) -> None:
        since = timezone.now() - timedelta(days=max(1, int(options["since_days"])))
        rows = list(
            AnalyticsEvent.objects.filter(occurred_at__gte=since)
            .values(
                "event_type",
                "properties__preset_id",
                "properties__outcome",
                "properties__reason",
            )
            .annotate(count=Count("id"))
            .order_by("event_type", "properties__preset_id")
        )
        normalized = [
            {
                "event_type": row["event_type"],
                "preset_id": row["properties__preset_id"],
                "outcome": row["properties__outcome"],
                "reason": row["properties__reason"],
                "count": row["count"],
            }
            for row in rows
        ]
        if options["format"] == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer, fieldnames=["event_type", "preset_id", "outcome", "reason", "count"]
            )
            writer.writeheader()
            writer.writerows(normalized)
            content = buffer.getvalue()
        else:
            content = json.dumps(normalized, indent=2, ensure_ascii=False)
        output: Path | None = options.get("output")
        if output is None:
            self.stdout.write(content)
        else:
            output.write_text(content, encoding="utf-8")
            self.stdout.write(str(output))
