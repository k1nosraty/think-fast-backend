import json
from dataclasses import fields
from typing import Protocol, cast

from apps.games.color import (
    ColorDefinition,
    ColorRules,
    ColorValidationError,
    evaluate_color,
    generate_color_secret,
    validate_color_sequence,
)
from apps.games.domain import GuessValidationError, NumberRules, evaluate_number, validate_sequence
from apps.games.secrets import generate_number_secret
from apps.games.word_spike import (
    WordRules,
    WordSpikeError,
    evaluate_word,
    generate_word_secret,
    normalize_persian_word,
)

Rules = NumberRules | ColorRules | WordRules


class GameAdapter(Protocol):
    def rules_from_snapshot(self, snapshot: dict[str, object]) -> Rules: ...

    def generate_secret(self, rules: Rules) -> object: ...

    def encode_secret(self, rules: Rules, secret: object) -> str: ...

    def decode_secret(self, rules: Rules, value: str) -> object: ...

    def evaluate(
        self, rules: Rules, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]: ...


class NumberAdapter:
    def rules_from_snapshot(self, snapshot: dict[str, object]) -> Rules:
        return NumberRules(**{field.name: snapshot[field.name] for field in fields(NumberRules)})  # type: ignore[arg-type]

    def generate_secret(self, rules: Rules) -> object:
        return generate_number_secret(cast(NumberRules, rules))

    def encode_secret(self, rules: Rules, secret: object) -> str:
        return validate_sequence(cast(str, secret), cast(NumberRules, rules))

    def decode_secret(self, rules: Rules, value: str) -> object:
        return validate_sequence(value, cast(NumberRules, rules))

    def evaluate(
        self, rules: Rules, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]:
        if not isinstance(guess, str):
            raise GuessValidationError("invalid_symbol")
        number_rules = cast(NumberRules, rules)
        canonical = validate_sequence(guess, number_rules)
        positions, solved = evaluate_number(
            rules=number_rules, secret=cast(str, secret), guess=canonical
        )
        return canonical, {"kind": "positional", "positions": positions}, solved


class ColorAdapter:
    def rules_from_snapshot(self, snapshot: dict[str, object]) -> Rules:
        values = dict(snapshot)
        values["palette"] = tuple(
            ColorDefinition(**item) for item in cast(list[dict[str, str]], snapshot["palette"])
        )
        return ColorRules(**{field.name: values[field.name] for field in fields(ColorRules)})  # type: ignore[arg-type]

    def generate_secret(self, rules: Rules) -> object:
        return generate_color_secret(cast(ColorRules, rules))

    def encode_secret(self, rules: Rules, secret: object) -> str:
        canonical = validate_color_sequence(secret, cast(ColorRules, rules))
        return json.dumps(canonical, separators=(",", ":"))

    def decode_secret(self, rules: Rules, value: str) -> object:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ColorValidationError("invalid_symbol") from exc
        return validate_color_sequence(parsed, cast(ColorRules, rules))

    def evaluate(
        self, rules: Rules, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]:
        color_rules = cast(ColorRules, rules)
        canonical = validate_color_sequence(guess, color_rules)
        feedback, solved = evaluate_color(rules=color_rules, secret=secret, guess=canonical)
        return canonical, feedback, solved


REGISTRY: dict[str, GameAdapter] = {"number": NumberAdapter(), "color": ColorAdapter()}


def adapter_for(game_type: object) -> GameAdapter:
    adapter = REGISTRY.get(str(game_type))
    if adapter is None:
        raise ValueError("unsupported game_type")
    return adapter


def rules_from_snapshot(snapshot: dict[str, object]) -> Rules:
    return adapter_for(snapshot.get("game_type")).rules_from_snapshot(snapshot)


class WordAdapter:
    def __init__(self) -> None:
        from apps.games.word_lexicon import get_placeholder_lexicon

        self._lexicon = get_placeholder_lexicon()

    def rules_from_snapshot(self, snapshot: dict[str, object]) -> Rules:
        return WordRules(**{field.name: snapshot[field.name] for field in fields(WordRules)})  # type: ignore[arg-type]

    def generate_secret(self, rules: Rules) -> object:
        return generate_word_secret(cast(WordRules, rules), self._lexicon)

    def encode_secret(self, rules: Rules, secret: object) -> str:
        return normalize_persian_word(secret)

    def decode_secret(self, rules: Rules, value: str) -> object:
        return normalize_persian_word(value)

    def evaluate(
        self, rules: Rules, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]:
        if not isinstance(guess, str):
            raise WordSpikeError("invalid_symbol")
        word_rules = cast(WordRules, rules)
        canonical = normalize_persian_word(guess)
        self._lexicon.validate(canonical, length=word_rules.sequence_length)
        secret_canonical = cast(str, secret)
        positions, solved = evaluate_word(secret=secret_canonical, guess=canonical)
        return canonical, {"kind": "positional", "positions": positions}, solved


REGISTRY["word"] = WordAdapter()
