from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_publish_outbox_command_reports_delivered_and_attempted() -> None:
    output = StringIO()
    with patch(
        "apps.realtime.management.commands.publish_outbox.publish_pending",
        return_value=(3, 5),
    ) as mocked:
        call_command("publish_outbox", stdout=output)
    mocked.assert_called_once_with(limit=100)
    assert output.getvalue() == "outbox attempted=5 delivered=3\n"


@pytest.mark.django_db
def test_publish_outbox_command_forwards_explicit_limit() -> None:
    output = StringIO()
    with patch(
        "apps.realtime.management.commands.publish_outbox.publish_pending",
        return_value=(0, 0),
    ) as mocked:
        call_command("publish_outbox", limit=7, stdout=output)
    mocked.assert_called_once_with(limit=7)


@pytest.mark.django_db
def test_sweep_reliability_command_reports_every_recovery_bucket() -> None:
    output = StringIO()
    with patch(
        "apps.realtime.management.commands.sweep_reliability.sweep_reliability",
        return_value={
            "challenge_setups_expired": 1,
            "countdowns": 2,
            "matches": 3,
            "abandoned": 0,
            "rematches_expired": 1,
            "outbox_attempted": 4,
            "outbox_delivered": 4,
        },
    ) as mocked:
        call_command("sweep_reliability", stdout=output)
    mocked.assert_called_once_with(limit=100)
    assert "challenge_setups_expired=1" in output.getvalue()
    assert "matches=3" in output.getvalue()
    assert "outbox_delivered=4" in output.getvalue()


@pytest.mark.django_db
def test_sweep_reliability_command_forwards_explicit_limit() -> None:
    output = StringIO()
    with patch(
        "apps.realtime.management.commands.sweep_reliability.sweep_reliability",
        return_value={},
    ) as mocked:
        call_command("sweep_reliability", limit=3, stdout=output)
    mocked.assert_called_once_with(limit=3)
