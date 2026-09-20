"""Shared positional feedback evaluator (Wordle-style duplicate-safe algorithm)."""

from collections import Counter
from collections.abc import Sequence
from typing import Literal

FeedbackToken = Literal["exact", "present", "absent"]


def positional_feedback(
    secret: Sequence[str], guess: Sequence[str]
) -> tuple[list[FeedbackToken], bool]:
    """Wordle-style duplicate-safe positional feedback evaluator."""
    if len(secret) != len(guess):
        raise ValueError("invalid_guess_length")
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
