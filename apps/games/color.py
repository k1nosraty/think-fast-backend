import secrets
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from apps.games.feedback import positional_feedback


@dataclass(frozen=True)
class ColorDefinition:
    color_id: str
    hex: str
    label_key: str
    shape: str
    pattern: str


COLOR_PALETTE = (
    ColorDefinition("red", "#D64545", "color.red", "circle", "solid"),
    ColorDefinition("orange", "#E67E22", "color.orange", "triangle", "dots"),
    ColorDefinition("yellow", "#F1C40F", "color.yellow", "diamond", "stripes"),
    ColorDefinition("green", "#27AE60", "color.green", "square", "crosshatch"),
    ColorDefinition("cyan", "#16A6B6", "color.cyan", "hexagon", "waves"),
    ColorDefinition("blue", "#2E6BD1", "color.blue", "star", "grid"),
    ColorDefinition("indigo", "#4B4FAE", "color.indigo", "pentagon", "diagonal"),
    ColorDefinition("violet", "#8E44AD", "color.violet", "heart", "rings"),
    ColorDefinition("magenta", "#C23B8E", "color.magenta", "cross", "zigzag"),
    ColorDefinition("rose", "#E85D75", "color.rose", "flower", "speckle"),
    ColorDefinition("brown", "#8D6E63", "color.brown", "shield", "brick"),
    ColorDefinition("slate", "#607D8B", "color.slate", "octagon", "checker"),
)
_SYSTEM_RANDOM = secrets.SystemRandom()


@dataclass(frozen=True)
class ColorRules:
    preset_id: str
    game_type: Literal["color"]
    match_mode: Literal["practice", "friendly"]
    schema_version: int
    evaluator_version: int
    variant: Literal["classic", "permutation"]
    palette: tuple[ColorDefinition, ...]
    sequence_length: int
    allow_duplicates: bool
    max_symbol_repetition: int
    feedback_policy: Literal["positional", "aggregate", "exact_count"]
    history_policy: dict[str, object]
    match_deadline_seconds: int
    attempt_limit: int

    def snapshot(self) -> dict[str, object]:
        return asdict(self)


COLOR_PRESETS = {
    "color_classic_5_v1": ColorRules(
        "color_classic_5_v1",
        "color",
        "practice",
        1,
        1,
        "classic",
        COLOR_PALETTE,
        5,
        True,
        2,
        "aggregate",
        {"type": "full"},
        180,
        12,
    ),
    "color_permutation_8_v1": ColorRules(
        "color_permutation_8_v1",
        "color",
        "practice",
        1,
        1,
        "permutation",
        COLOR_PALETTE[:8],
        8,
        False,
        1,
        "exact_count",
        {"type": "last_n", "count": 1},
        240,
        15,
    ),
}


class ColorValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def color_ids(rules: ColorRules) -> tuple[str, ...]:
    return tuple(item.color_id for item in rules.palette)


def validate_color_sequence(value: object, rules: ColorRules) -> list[str]:
    if not isinstance(value, list) or len(value) != rules.sequence_length:
        raise ColorValidationError("invalid_guess_length")
    if not all(isinstance(item, str) for item in value):
        raise ColorValidationError("invalid_symbol")
    guess = list(value)
    allowed = set(color_ids(rules))
    if any(item not in allowed for item in guess):
        raise ColorValidationError("invalid_symbol")
    counts = Counter(guess)
    if rules.variant == "permutation" and (
        len(counts) != rules.sequence_length or set(guess) != allowed
    ):
        raise ColorValidationError("invalid_permutation")
    if not rules.allow_duplicates and any(count > 1 for count in counts.values()):
        raise ColorValidationError("duplicate_not_allowed")
    if max(counts.values()) > rules.max_symbol_repetition:
        raise ColorValidationError("repetition_limit_exceeded")
    return guess


def evaluate_color(
    *, rules: ColorRules, secret: object, guess: object
) -> tuple[dict[str, object], bool]:
    canonical_secret = validate_color_sequence(secret, rules)
    canonical_guess = validate_color_sequence(guess, rules)
    tokens, solved = positional_feedback(canonical_secret, canonical_guess)
    exact_count = tokens.count("exact")
    if rules.feedback_policy == "positional":
        return {"kind": "positional", "positions": tokens}, solved
    if rules.feedback_policy == "aggregate":
        return {
            "kind": "aggregate",
            "exact_count": exact_count,
            "present_count": tokens.count("present"),
        }, solved
    return {"kind": "exact_count", "exact_count": exact_count}, solved


def generate_color_secret(
    rules: ColorRules,
    *,
    choice: Callable[[Sequence[str]], str] = secrets.choice,
    sample: Callable[[Sequence[str], int], list[str]] = _SYSTEM_RANDOM.sample,
) -> list[str]:
    available = color_ids(rules)
    if rules.variant == "permutation":
        return validate_color_sequence(sample(available, rules.sequence_length), rules)
    result: list[str] = []
    while len(result) < rules.sequence_length:
        symbol = choice(available)
        if Counter(result)[symbol] < rules.max_symbol_repetition:
            result.append(symbol)
    return validate_color_sequence(result, rules)
