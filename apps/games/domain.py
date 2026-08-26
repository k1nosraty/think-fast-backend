from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Literal

FeedbackToken = Literal["exact", "present", "absent"]


@dataclass(frozen=True)
class NumberRules:
    preset_id: str
    game_type: Literal["number"]
    match_mode: Literal["practice", "friendly"]
    schema_version: int
    evaluator_version: int
    sequence_length: int
    allow_leading_zero: bool
    allow_duplicates: bool
    max_symbol_repetition: int
    feedback_policy: Literal["positional"]
    history_policy: dict[str, str]
    match_deadline_seconds: int
    attempt_limit: int

    def snapshot(self) -> dict[str, object]:
        return asdict(self)


NUMBER_PRESETS = {
    "number_classic_5_v1": NumberRules(
        "number_classic_5_v1",
        "number",
        "practice",
        1,
        1,
        5,
        False,
        True,
        2,
        "positional",
        {"type": "full"},
        180,
        12,
    ),
    "number_brain_burner_6_v1": NumberRules(
        "number_brain_burner_6_v1",
        "number",
        "practice",
        1,
        1,
        6,
        False,
        True,
        2,
        "positional",
        {"type": "full"},
        240,
        15,
    ),
}

from apps.games.color import COLOR_PRESETS, ColorRules  # noqa: E402

PRESETS: dict[str, NumberRules | ColorRules] = {**NUMBER_PRESETS, **COLOR_PRESETS}


def rules_for_mode(
    preset_id: str, mode: Literal["practice", "friendly"]
) -> NumberRules | ColorRules | None:
    rules = PRESETS.get(preset_id)
    if rules is None:
        return None
    return replace(rules, match_mode=mode)


class GuessValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_sequence(value: str, rules: NumberRules) -> str:
    if len(value) != rules.sequence_length:
        raise GuessValidationError("invalid_guess_length")
    if not value.isascii() or not value.isdigit():
        raise GuessValidationError("invalid_symbol")
    if not rules.allow_leading_zero and value.startswith("0"):
        raise GuessValidationError("leading_zero_not_allowed")
    counts = Counter(value)
    if not rules.allow_duplicates and max(counts.values()) > 1:
        raise GuessValidationError("duplicate_not_allowed")
    if max(counts.values()) > rules.max_symbol_repetition:
        raise GuessValidationError("repetition_limit_exceeded")
    return value


def evaluate_number(
    *, rules: NumberRules, secret: str, guess: str
) -> tuple[list[FeedbackToken], bool]:
    validate_sequence(secret, rules)
    validate_sequence(guess, rules)
    feedback: list[FeedbackToken | None] = [None] * len(secret)
    remaining: Counter[str] = Counter()
    for index, (secret_symbol, guess_symbol) in enumerate(zip(secret, guess, strict=True)):
        if secret_symbol == guess_symbol:
            feedback[index] = "exact"
        else:
            remaining[secret_symbol] += 1
    for index, guess_symbol in enumerate(guess):
        if feedback[index] == "exact":
            continue
        if remaining[guess_symbol] > 0:
            feedback[index] = "present"
            remaining[guess_symbol] -= 1
        else:
            feedback[index] = "absent"
    result = [token for token in feedback if token is not None]
    return result, all(token == "exact" for token in result)
