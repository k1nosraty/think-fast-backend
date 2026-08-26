import json
from pathlib import Path

import pytest

from apps.games.domain import (
    NUMBER_PRESETS,
    GuessValidationError,
    evaluate_number,
    validate_sequence,
)
from apps.games.secrets import generate_number_secret


def test_canonical_feedback_matrix() -> None:
    cases = json.loads(
        (
            Path(__file__).resolve().parents[3] / "contracts/fixtures/number-feedback-cases.json"
        ).read_text()
    )["cases"]
    for case in cases:
        rules = NUMBER_PRESETS[case["preset_id"]]
        if case["valid"]:
            positions, solved = evaluate_number(
                rules=rules, secret=case["secret"], guess=case["guess"]
            )
            assert positions == case["expected"]["positions"], case["id"]
            assert solved is all(position == "exact" for position in positions), case["id"]
        else:
            with pytest.raises(GuessValidationError, match=case["expected"]["error_code"]):
                evaluate_number(rules=rules, secret=case["secret"], guess=case["guess"])


@pytest.mark.parametrize(
    ("guess", "code"),
    [
        ("1234", "invalid_guess_length"),
        ("12a45", "invalid_symbol"),
        ("01234", "leading_zero_not_allowed"),
        ("11123", "repetition_limit_exceeded"),
    ],
)
def test_guess_validation_errors(guess: str, code: str) -> None:
    with pytest.raises(GuessValidationError, match=code):
        validate_sequence(guess, NUMBER_PRESETS["number_classic_5_v1"])


def test_generator_is_injectable_and_obeys_repetition_cap() -> None:
    values = iter("112345")
    secret = generate_number_secret(
        NUMBER_PRESETS["number_classic_5_v1"], choice=lambda _: next(values)
    )
    assert secret == "11234"
