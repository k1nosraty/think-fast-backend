"""Word game adapter: Persian Wordle-style evaluation with bounded lexicon."""

import secrets as _secrets
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from apps.games.feedback import positional_feedback

WordFeedbackToken = Literal["exact", "present", "absent"]

_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_IGNORABLE_SPACING = {" ", "\t", "\n", "\r", "\u200c", "\u200d", "\ufeff"}


class WordSpikeError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def normalize_persian_word(value: object) -> str:
    if not isinstance(value, str):
        raise WordSpikeError("invalid_symbol")
    normalized = unicodedata.normalize("NFC", value).translate(_ARABIC_TO_PERSIAN)
    canonical = "".join(
        character
        for character in normalized
        if character not in _IGNORABLE_SPACING
        and character != "ـ"
        and unicodedata.category(character) != "Mn"
    )
    if not canonical:
        raise WordSpikeError("invalid_word")
    if any(not ("آ" <= character <= "ی") for character in canonical):
        raise WordSpikeError("invalid_symbol")
    return canonical


@dataclass(frozen=True)
class WordEntry:
    canonical: str
    part_of_speech: str
    frequency_rank: int
    is_proper_name: bool = False


class BoundedLexicon:
    def __init__(self, entries: list[WordEntry], blocked_terms: set[str] | None = None) -> None:
        self._entries = {normalize_persian_word(item.canonical): item for item in entries}
        self._blocked = {normalize_persian_word(item) for item in (blocked_terms or set())}

    def validate(self, value: object, *, length: int) -> str:
        canonical = normalize_persian_word(value)
        if len(canonical) != length:
            raise WordSpikeError("invalid_guess_length")
        if canonical in self._blocked:
            raise WordSpikeError("word_blocked")
        entry = self._entries.get(canonical)
        if entry is None or entry.is_proper_name:
            raise WordSpikeError("word_not_in_dictionary")
        return canonical


def evaluate_word(secret: str, guess: str) -> tuple[list[WordFeedbackToken], bool]:
    if len(secret) != len(guess):
        raise WordSpikeError("invalid_guess_length")
    tokens, solved = positional_feedback(secret, guess)
    return tokens, solved


@dataclass(frozen=True)
class WordRules:
    preset_id: str
    game_type: Literal["word"]
    match_mode: Literal["practice", "friendly"]
    schema_version: int
    evaluator_version: int
    sequence_length: int
    lexicon_version: str
    alphabet: str
    feedback_policy: Literal["positional"]
    history_policy: dict[str, str]
    match_deadline_seconds: int
    attempt_limit: int

    def snapshot(self) -> dict[str, object]:
        return asdict(self)


WORD_PRESETS = {
    "word_classic_5_fa_v1": WordRules(
        "word_classic_5_fa_v1",
        "word",
        "practice",
        1,
        1,
        5,
        "placeholder-v1",
        "fa",
        "positional",
        {"type": "full"},
        240,
        15,
    ),
}


def generate_word_secret(
    rules: WordRules,
    lexicon: "BoundedLexicon",
    choice: Callable[[Sequence[str]], str] = _secrets.choice,
) -> str:
    candidates = [
        entry.canonical
        for entry in lexicon._entries.values()
        if not entry.is_proper_name and len(entry.canonical) == rules.sequence_length
    ]
    if not candidates:
        raise WordSpikeError("word_not_in_dictionary")
    return choice(candidates)
