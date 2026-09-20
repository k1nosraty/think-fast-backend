"""Number game engine: rules, sequence validation, evaluation, and adapter."""

from collections import Counter
from dataclasses import asdict, dataclass, fields
from typing import Literal, cast

from apps.games.base import GameValidationError
from apps.games.feedback import FeedbackToken, positional_feedback


class GuessValidationError(GameValidationError):
    """Validation error specific to number sequence guesses."""


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


NUMBER_PRESETS: dict[str, NumberRules] = {
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
    return positional_feedback(secret, guess)


class NumberAdapter:
    def rules_from_snapshot(self, snapshot: dict[str, object]) -> NumberRules:
        return NumberRules(**{field.name: snapshot[field.name] for field in fields(NumberRules)})  # type: ignore[arg-type]

    def generate_secret(self, rules: object) -> str:
        import apps.games.registry as reg

        generator = getattr(reg, "generate_number_secret", None)
        if generator is None:
            from apps.games.secrets import generate_number_secret

            generator = generate_number_secret
        return generator(cast(NumberRules, rules))

    def encode_secret(self, rules: object, secret: object) -> str:
        return validate_sequence(cast(str, secret), cast(NumberRules, rules))

    def decode_secret(self, rules: object, value: str) -> str:
        return validate_sequence(value, cast(NumberRules, rules))

    def evaluate(
        self, rules: object, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]:
        if not isinstance(guess, str):
            raise GuessValidationError("invalid_symbol")
        number_rules = cast(NumberRules, rules)
        canonical = validate_sequence(guess, number_rules)
        positions, solved = evaluate_number(
            rules=number_rules, secret=cast(str, secret), guess=canonical
        )
        return canonical, {"kind": "positional", "positions": positions}, solved
