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
    "CREATABLE_PRESET_IDS",
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

#: Presets a client is allowed to start a Match or Room with.
#:
#: The Word prototype is deliberately excluded while it stays gated (see the
#: workspace README): it is advertised through `/game-definitions/` so the
#: catalogue can label it as a prototype, but it cannot be instantiated. This
#: tuple is the single source of truth for that allowlist; the published request
#: contracts (`contracts/schemas/create-room-command.schema.json` and the
#: `/solo-matches/` request body) enumerate exactly the same four ids, and
#: `tests/contracts/test_contracts.py` fails if the two drift apart.
CREATABLE_PRESET_IDS: tuple[str, ...] = (
    "number_classic_5_v1",
    "number_brain_burner_6_v1",
    "color_classic_5_v1",
    "color_permutation_8_v1",
)


def rules_for_mode(
    preset_id: str, mode: Literal["practice", "friendly"]
) -> NumberRules | ColorRules | WordRules | None:
    rules = PRESETS.get(preset_id)
    if rules is None:
        return None
    return replace(rules, match_mode=mode)
