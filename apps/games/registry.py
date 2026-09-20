"""Game adapter registry mapping game_type strings to adapters."""

from dataclasses import fields
from typing import cast

from apps.games.base import GameAdapter
from apps.games.color import ColorAdapter, ColorRules, generate_color_secret
from apps.games.number import NumberAdapter, NumberRules
from apps.games.secrets import generate_number_secret
from apps.games.word_spike import (
    WordRules,
    WordSpikeError,
    evaluate_word,
    generate_word_secret,
    normalize_persian_word,
)

__all__ = [
    "REGISTRY",
    "ColorAdapter",
    "GameAdapter",
    "NumberAdapter",
    "Rules",
    "WordAdapter",
    "adapter_for",
    "generate_color_secret",
    "generate_number_secret",
]

Rules = NumberRules | ColorRules | WordRules


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


REGISTRY: dict[str, GameAdapter] = {
    "number": NumberAdapter(),
    "color": ColorAdapter(),
    "word": WordAdapter(),
}


def adapter_for(game_type: object) -> GameAdapter:
    adapter = REGISTRY.get(str(game_type))
    if adapter is None:
        raise ValueError("unsupported game_type")
    return adapter


def rules_from_snapshot(snapshot: dict[str, object]) -> Rules:
    return cast(Rules, adapter_for(snapshot.get("game_type")).rules_from_snapshot(snapshot))
