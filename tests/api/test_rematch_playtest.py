import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.analytics.models import AnalyticsEvent
from apps.games.secrets import decrypt_secret
from apps.matches.models import Match, RematchProposal
from apps.matches.rematches import expire_rematch_proposal
from tests.api.test_friendly_flow import active_match, command


def finish_match() -> tuple[object, object, dict[str, object]]:
    host, opponent, started = active_match()
    match_id = started["match_id"]
    host.post(f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json")
    opponent.post(f"/api/v1/matches/{match_id}/guesses/", command(guess="12345"), format="json")
    return host, opponent, started


@pytest.mark.django_db(transaction=True)
def test_full_rematch_creates_fresh_match_without_stale_private_state() -> None:
    host, opponent, started = finish_match()
    source = Match.objects.get(pk=started["match_id"])
    request_payload = command()
    requested = host.post(f"/api/v1/matches/{source.id}/rematch/", request_payload, format="json")
    retry = host.post(f"/api/v1/matches/{source.id}/rematch/", request_payload, format="json")
    assert requested.status_code == retry.status_code == 202
    assert requested.data == retry.data
    assert requested.data["rematch"]["state"] == "pending"

    with patch("apps.games.registry.generate_number_secret", return_value="54321"):
        accepted = opponent.post(f"/api/v1/matches/{source.id}/rematch/", command(), format="json")
    assert accepted.status_code == 202
    assert accepted.data["rematch"]["state"] == "accepted"
    new_match = Match.objects.get(pk=accepted.data["latest_match_id"])
    assert new_match.id != source.id
    assert new_match.rules == source.rules
    assert decrypt_secret(new_match.challenge.protected_secret) == "54321"
    assert new_match.participants.count() == source.participants.count() == 2
    assert new_match.participants.filter(attempt_count=0).count() == 2
    assert not new_match.participants.filter(attempts__isnull=False).exists()

    host_snapshot = host.get(f"/api/v1/matches/{new_match.id}/snapshot/").data
    opponent_snapshot = opponent.get(f"/api/v1/matches/{new_match.id}/snapshot/").data
    assert host_snapshot["own_attempts"] == opponent_snapshot["own_attempts"] == []
    assert "12345" not in json.dumps(host_snapshot)
    assert "12345" not in json.dumps(opponent_snapshot)
    assert source.result.outcome == "draw"
    stale = host.post(f"/api/v1/matches/{source.id}/rematch/", command(), format="json")
    assert stale.status_code == 409
    assert Match.objects.filter(room=source.room).count() == 2


@pytest.mark.django_db(transaction=True)
@override_settings(REMATCH_REQUEST_TTL_SECONDS=10)
def test_rematch_decline_and_expiry_are_explicit_and_recoverable() -> None:
    host, opponent, started = finish_match()
    match_id = started["match_id"]
    host.post(f"/api/v1/matches/{match_id}/rematch/", command(), format="json")
    declined = opponent.post(
        f"/api/v1/matches/{match_id}/rematch/",
        command(action="decline"),
        format="json",
    )
    assert declined.status_code == 202
    assert declined.data["rematch"]["state"] == "declined"
    assert declined.data["state"] == "ready_check"

    host.post(f"/api/v1/matches/{match_id}/rematch/", command(), format="json")
    proposal = RematchProposal.objects.get(source_match_id=match_id)
    assert expire_rematch_proposal(proposal.id, now=proposal.expires_at + timedelta(milliseconds=1))
    proposal.refresh_from_db()
    assert proposal.state == RematchProposal.State.EXPIRED
    assert AnalyticsEvent.objects.filter(event_type="rematch_declined").count() == 1
    assert AnalyticsEvent.objects.filter(event_type="rematch_expired").count() == 1


@pytest.mark.django_db(transaction=True)
def test_analytics_and_export_are_aggregate_and_secret_free() -> None:
    host, _, started = active_match()
    match_id = started["match_id"]
    invalid = host.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="11111"), format="json"
    )
    accepted = host.post(
        f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
    )
    assert invalid.status_code == 400
    assert accepted.status_code == 201
    events = list(AnalyticsEvent.objects.all())
    serialized = json.dumps([item.properties for item in events])
    assert "11111" not in serialized
    assert "54321" not in serialized
    assert "12345" not in serialized
    assert AnalyticsEvent.objects.filter(event_type="invalid_guess").exists()
    assert AnalyticsEvent.objects.filter(event_type="attempt_accepted").exists()

    output = StringIO()
    call_command("export_playtest_analytics", format="json", since_days=1, stdout=output)
    exported = output.getvalue()
    assert "invalid_guess" in exported
    assert "attempt_accepted" in exported
    assert str(match_id) not in exported
    assert "12345" not in exported


@pytest.mark.django_db(transaction=True)
def test_analytics_port_rejects_private_or_unknown_properties() -> None:
    from apps.analytics.service import record_analytics

    with pytest.raises(ValueError, match="unsafe"):
        record_analytics("attempt_accepted", guess="12345")
    with pytest.raises(ValueError, match="unsupported"):
        record_analytics("raw_payload", preset_id="number_classic_5_v1")


@pytest.mark.django_db(transaction=True)
def test_guess_throttle_records_only_aggregate_spam_event() -> None:
    host, _, started = active_match()
    match_id = started["match_id"]
    with patch(
        "apps.analytics.throttles.AnalyticsScopedRateThrottle.get_rate", return_value="1/min"
    ):
        first = host.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="54321"), format="json"
        )
        blocked = host.post(
            f"/api/v1/matches/{match_id}/guesses/", command(guess="67890"), format="json"
        )
    assert first.status_code == 201
    assert blocked.status_code == 429
    event = AnalyticsEvent.objects.get(event_type="spam_blocked")
    assert event.properties["reason"] == "rate_limit"
    assert "67890" not in json.dumps(event.properties)


@pytest.mark.django_db(transaction=True)
def test_playtest_seed_and_csv_export_commands_are_runnable() -> None:
    seeded = StringIO()
    call_command("seed_playtest", stdout=seeded)
    output = seeded.getvalue()
    assert "room_id=" in output
    assert "match_id=" in output
    assert "host_token=" in output
    assert "opponent_token=" in output
    assert Match.objects.filter(room__isnull=False).count() == 1

    exported = StringIO()
    call_command("export_playtest_analytics", format="csv", since_days=1, stdout=exported)
    assert exported.getvalue().startswith("event_type,preset_id,outcome,reason,count")
