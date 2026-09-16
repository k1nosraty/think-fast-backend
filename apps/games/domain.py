"""Domain rules facade aggregating presets across all game modes."""

from dataclasses import replace
from typing import Literal

from apps.games.color import COLOR_PRESETS, ColorRules
from apps.games.number import (
    NUMBER_PRESETS,
    GuessValidationError,
    NumberRules,
    evaluate_number,
    validate_sequence,
)
from apps.games.word_spike import WORD_PRESETS, WordRules

# Re-export for backward compatibility
__all__ = [
    "COLOR_PRESETS",
    "NUMBER_PRESETS",
    "PRESETS",
    "WORD_PRESETS",
    "ColorRules",
    "GuessValidationError",
    "NumberRules",
    "WordRules",
    "evaluate_number",
    "rules_for_mode",
    "validate_sequence",
]

PRESETS: dict[str, NumberRules | ColorRules | WordRules] = {
    **NUMBER_PRESETS,
    **COLOR_PRESETS,
    **WORD_PRESETS,
}


def rules_for_mode(
    preset_id: str, mode: Literal["practice", "friendly"]
) -> NumberRules | ColorRules | WordRules | None:
    rules = PRESETS.get(preset_id)
    if rules is None:
        return None
    return replace(rules, match_mode=mode)
