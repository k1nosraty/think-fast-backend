import json
import stat
import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from apps.analytics.models import OperationalAuditEvent
from apps.matches.models import Attempt, Challenge, Match, Result
from tests.api.test_friendly_flow import command, guest


@pytest.mark.django_db
@override_settings(METRICS_BEARER_TOKEN="metrics-token-with-more-than-32-characters")
def test_metrics_are_hidden_and_contain_only_aggregate_values(client: Client) -> None:
    assert client.get("/metrics/").status_code == 404
    response = client.get(
        "/metrics/",
        headers={"Authorization": "Bearer metrics-token-with-more-than-32-characters"},
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "think_fast_matches_active" in body
    assert "think_fast_http_requests_total" in body
    assert "token" not in body.lower()
    assert "12345" not in body
    assert "54321" not in body
    assert "authorization" not in body.lower()


@pytest.mark.django_db
@override_settings(ENABLE_MATCH_CREATION=False)
def test_match_creation_kill_switch_fails_closed() -> None:
    client, _ = guest("Amir", "avatar_01")
    response = client.post(
        "/api/v1/solo-matches/",
        command(preset_id="number_classic_5_v1"),
        format="json",
    )
    assert response.status_code == 503
    assert response.data["code"] == "feature_disabled"
    assert Match.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    SECRET_RETENTION_HOURS=24,
    ATTEMPT_RETENTION_DAYS=90,
    MATCH_RETENTION_DAYS=365,
    GUEST_RETENTION_DAYS=30,
)
def test_retention_dry_run_then_destroys_sensitive_data_with_audit() -> None:
    client, _ = guest("Amir", "avatar_01")
    created = client.post(
        "/api/v1/solo-matches/",
        command(preset_id="number_classic_5_v1"),
        format="json",
    )
    match = Match.objects.get(pk=created.data["match_id"])
    participant = match.participants.get()
    old = timezone.now() - timedelta(days=91)
    match.state = Match.State.FINISHED
    match.finished_at = timezone.now() - timedelta(hours=25)
    match.save(update_fields=["state", "finished_at"])
    Result.objects.create(
        match=match,
        outcome="unsolved",
        reason="deadline",
        secret_revealed=True,
    )
    Attempt.objects.create(
        participant=participant,
        command_id=uuid.uuid4(),
        request_fingerprint="a" * 64,
        ordinal=1,
        guess="54321",
        feedback={"kind": "positional", "positions": ["absent"] * 5},
        accepted_at=old,
    )
    participant.guest.last_seen_at = timezone.now() - timedelta(days=31)
    participant.guest.expires_at = timezone.now() - timedelta(days=1)
    participant.guest.save(update_fields=["last_seen_at", "expires_at"])

    preview = StringIO()
    call_command("apply_retention", stdout=preview)
    assert "dry_run=true" in preview.getvalue()
    assert Attempt.objects.filter(participant=participant).exists()

    applied = StringIO()
    call_command("apply_retention", apply=True, actor="retention-test", stdout=applied)
    challenge = Challenge.objects.get(match=match)
    participant.guest.refresh_from_db()
    match.result.refresh_from_db()
    assert challenge.protected_secret == ""
    assert challenge.secret_destroyed_at is not None
    assert not match.result.secret_revealed
    assert not Attempt.objects.filter(participant=participant).exists()
    assert participant.guest.display_name == "Deleted Player"
    audit = OperationalAuditEvent.objects.get(action="retention.applied")
    assert audit.actor == "retention-test"
    assert "54321" not in json.dumps(audit.counts)


@pytest.mark.django_db
@override_settings(LOAD_FIXTURES_ENABLED=True)
def test_load_fixture_generation_is_explicit_and_private(tmp_path: Path) -> None:
    output = tmp_path / "load.json"
    call_command("prepare_load_fixtures", count=1, output=str(output))
    rows = json.loads(output.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert set(rows[0]) == {"match_id", "token", "guess"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert Match.objects.filter(state=Match.State.ACTIVE).count() == 1
