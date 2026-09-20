from django.conf import settings

from apps.matches.errors import GameAPIError


def require_match_creation() -> None:
    if not settings.ENABLE_MATCH_CREATION:
        raise GameAPIError(
            "feature_disabled", "New Match creation is temporarily disabled.", status_code=503
        )


def require_player_authored_challenges() -> None:
    if not settings.ENABLE_PLAYER_AUTHORED_CHALLENGES:
        raise GameAPIError(
            "feature_disabled",
            "Player-authored Challenges are temporarily disabled.",
            status_code=503,
        )
