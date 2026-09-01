import pytest
from django.test import override_settings

from apps.matches.errors import GameAPIError
from apps.matches.features import require_match_creation, require_player_authored_challenges


def test_match_creation_is_allowed_by_default() -> None:
    require_match_creation()


@override_settings(ENABLE_MATCH_CREATION=False)
def test_match_creation_fails_closed_when_disabled() -> None:
    with pytest.raises(GameAPIError) as exc_info:
        require_match_creation()
    assert exc_info.value.default_code == "feature_disabled"
    assert exc_info.value.status_code == 503


def test_player_authored_challenges_are_allowed_by_default() -> None:
    require_player_authored_challenges()


@override_settings(ENABLE_PLAYER_AUTHORED_CHALLENGES=False)
def test_player_authored_challenges_fail_closed_when_disabled() -> None:
    with pytest.raises(GameAPIError) as exc_info:
        require_player_authored_challenges()
    assert exc_info.value.default_code == "feature_disabled"
    assert exc_info.value.status_code == 503