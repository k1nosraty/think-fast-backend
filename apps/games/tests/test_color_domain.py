from dataclasses import replace

import pytest

from apps.games.color import (
    COLOR_PALETTE,
    COLOR_PRESETS,
    ColorValidationError,
    evaluate_color,
    generate_color_secret,
    validate_color_sequence,
)


def test_palette_has_stable_non_color_accessibility_metadata() -> None:
    assert len(COLOR_PALETTE) == 12
    assert len({item.color_id for item in COLOR_PALETTE}) == 12
    assert all(item.hex.startswith("#") for item in COLOR_PALETTE)
    assert all(item.label_key and item.shape and item.pattern for item in COLOR_PALETTE)


def test_classic_duplicate_safe_aggregate_and_positional_policies() -> None:
    rules = COLOR_PRESETS["color_classic_5_v1"]
    secret = ["red", "red", "blue", "green", "yellow"]
    guess = ["red", "blue", "red", "slate", "green"]
    aggregate, solved = evaluate_color(rules=rules, secret=secret, guess=guess)
    assert aggregate == {"kind": "aggregate", "exact_count": 1, "present_count": 3}
    assert solved is False

    positional_rules = replace(rules, feedback_policy="positional")
    positional, _ = evaluate_color(rules=positional_rules, secret=secret, guess=guess)
    assert positional == {
        "kind": "positional",
        "positions": ["exact", "present", "present", "absent", "present"],
    }


@pytest.mark.parametrize(
    ("guess", "code"),
    [
        (["red"] * 5, "repetition_limit_exceeded"),
        (["red", "orange", "yellow", "green"], "invalid_guess_length"),
        (["red", "orange", "yellow", "green", "unknown"], "invalid_symbol"),
    ],
)
def test_classic_validation(guess: list[str], code: str) -> None:
    with pytest.raises(ColorValidationError, match=code):
        validate_color_sequence(guess, COLOR_PRESETS["color_classic_5_v1"])


def test_permutation_requires_exact_set_and_returns_only_exact_count() -> None:
    rules = COLOR_PRESETS["color_permutation_8_v1"]
    secret = [item.color_id for item in rules.palette]
    guess = [*secret[1:], secret[0]]
    feedback, solved = evaluate_color(rules=rules, secret=secret, guess=guess)
    assert feedback == {"kind": "exact_count", "exact_count": 0}
    assert solved is False
    with pytest.raises(ColorValidationError, match="invalid_permutation"):
        validate_color_sequence([secret[0], secret[0], *secret[2:]], rules)


def test_color_generator_is_injectable_for_both_variants() -> None:
    classic = COLOR_PRESETS["color_classic_5_v1"]
    values = iter(["red", "red", "blue", "green", "yellow"])
    assert generate_color_secret(classic, choice=lambda _: next(values)) == [
        "red",
        "red",
        "blue",
        "green",
        "yellow",
    ]
    permutation = COLOR_PRESETS["color_permutation_8_v1"]
    reversed_ids = [item.color_id for item in reversed(permutation.palette)]
    assert (
        generate_color_secret(permutation, sample=lambda _, length: reversed_ids[:length])
        == reversed_ids
    )
