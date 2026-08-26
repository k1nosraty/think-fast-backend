"""Bounded T7 feasibility prototype; deliberately not registered as a Game Type."""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

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
    feedback: list[WordFeedbackToken | None] = [None] * len(secret)
    remaining: Counter[str] = Counter()
    for index, (secret_symbol, guess_symbol) in enumerate(zip(secret, guess, strict=True)):
        if secret_symbol == guess_symbol:
            feedback[index] = "exact"
        else:
            remaining[secret_symbol] += 1
    for index, guess_symbol in enumerate(guess):
        if feedback[index] == "exact":
            continue
        if remaining[guess_symbol]:
            feedback[index] = "present"
            remaining[guess_symbol] -= 1
        else:
            feedback[index] = "absent"
    result = [item for item in feedback if item is not None]
    return result, all(item == "exact" for item in result)
