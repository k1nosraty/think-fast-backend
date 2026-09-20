from typing import cast

import pytest

from apps.games.color import ColorRules, ColorValidationError
from apps.games.domain import GuessValidationError, NumberRules, rules_for_mode
from apps.games.registry import (
    ColorAdapter,
    NumberAdapter,
    adapter_for,
    rules_from_snapshot,
)
from apps.games.secrets import generate_number_secret


def _number_rules() -> NumberRules:
    rules = rules_for_mode("number_classic_5_v1", "practice")
    assert isinstance(rules, NumberRules)
    return rules


def _color_rules() -> ColorRules:
    rules = rules_for_mode("color_classic_5_v1", "practice")
    assert isinstance(rules, ColorRules)
    return rules


def test_adapter_for_unsupported_game_type_raises() -> None:
    with pytest.raises(ValueError, match="unsupported game_type"):
        adapter_for("tetris")
    with pytest.raises(ValueError, match="unsupported game_type"):
        rules_from_snapshot({"game_type": "unknown", "sequence_length": 5})


def test_number_adapter_rejects_non_string_guess() -> None:
    rules = _number_rules()
    adapter = NumberAdapter()
    secret = generate_number_secret(rules)
    with pytest.raises(GuessValidationError, match="invalid_symbol"):
        adapter.evaluate(rules, secret, ["1", "2", "3", "4", "5"])


def test_number_adapter_roundtrips_known_snapshot() -> None:
    adapter = NumberAdapter()
    snapshot = _number_rules().snapshot()
    restored = rules_from_snapshot(snapshot)
    assert isinstance(restored, NumberRules)
    assert restored.preset_id == "number_classic_5_v1"
    assert len(cast(str, adapter.generate_secret(restored))) == restored.sequence_length


def test_color_adapter_rejects_malformed_json_secret() -> None:
    rules = _color_rules()
    adapter = ColorAdapter()
    with pytest.raises(ColorValidationError, match="invalid_symbol"):
        adapter.decode_secret(rules, "{not-json")


def test_color_adapter_evaluates_and_roundtrips() -> None:
    rules = _color_rules()
    adapter = ColorAdapter()
    secret = ["red", "blue", "green", "yellow", "cyan"]
    encoded = adapter.encode_secret(rules, secret)
    decoded = adapter.decode_secret(rules, encoded)
    assert decoded == secret
    canonical, feedback, solved = adapter.evaluate(rules, secret, secret)
    assert canonical == secret
    assert solved is True
    assert feedback["kind"] == "aggregate"
    assert feedback["exact_count"] == rules.sequence_length


def test_color_adapter_generates_valid_secret() -> None:
    rules = _color_rules()
    adapter = ColorAdapter()
    assert len(cast(list[str], adapter.generate_secret(rules))) == rules.sequence_length
