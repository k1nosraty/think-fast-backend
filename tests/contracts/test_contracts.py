from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_contracts.py"
SPEC = importlib.util.spec_from_file_location("validate_contracts", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def reference_feedback(secret: str, guess: str) -> list[str]:
    result = ["absent"] * len(secret)
    remaining: Counter[str] = Counter()
    for index, (secret_symbol, guess_symbol) in enumerate(zip(secret, guess, strict=True)):
        if secret_symbol == guess_symbol:
            result[index] = "exact"
        else:
            remaining[secret_symbol] += 1
    for index, guess_symbol in enumerate(guess):
        if result[index] == "exact":
            continue
        if remaining[guess_symbol] > 0:
            result[index] = "present"
            remaining[guess_symbol] -= 1
    return result


def expected_validation_error(guess: str, length: int) -> str | None:
    if len(guess) != length:
        return "invalid_guess_length"
    if not guess.isascii() or not guess.isdigit():
        return "invalid_symbol"
    if guess.startswith("0"):
        return "leading_zero_not_allowed"
    if max(Counter(guess).values()) > 2:
        return "repetition_limit_exceeded"
    return None


class ContractTest(unittest.TestCase):
    def test_all_manifest_fixtures_validate(self) -> None:
        self.assertEqual(validator.validate_contracts(), 8)

    def test_number_feedback_examples_are_semantically_correct(self) -> None:
        fixture = json.loads(
            (ROOT / "contracts/fixtures/number-feedback-cases.json").read_text(encoding="utf-8")
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                length = 5 if case["preset_id"] == "number_classic_5_v1" else 6
                error = expected_validation_error(case["guess"], length)
                if case["valid"]:
                    self.assertIsNone(error)
                    self.assertEqual(
                        reference_feedback(case["secret"], case["guess"]),
                        case["expected"]["positions"],
                    )
                else:
                    self.assertEqual(error, case["expected"]["error_code"])

    def test_public_event_fixture_rejects_private_guess(self) -> None:
        schema_path = ROOT / "contracts/schemas/event.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        event = json.loads(
            (ROOT / "contracts/fixtures/events/opponent-guessed.json").read_text(encoding="utf-8")
        )
        event["payload"]["guess"] = "11234"
        with self.assertRaises(validator.ContractValidationError):
            validator.validate(event, schema, schema_path)

    def test_snapshot_fixture_rejects_opponent_private_data(self) -> None:
        snapshot = json.loads(
            (ROOT / "contracts/fixtures/snapshots/friendly-active.json").read_text(encoding="utf-8")
        )
        snapshot["opponent_guess"] = "112233"
        with self.assertRaises(validator.ContractValidationError):
            validator._assert_no_private_keys(snapshot, "snapshot")

    def test_feedback_schema_rejects_ambiguous_variant(self) -> None:
        schema_path = ROOT / "contracts/schemas/feedback.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        ambiguous = {"kind": "positional", "positions": ["exact"], "exact_count": 1}
        with self.assertRaises(validator.ContractValidationError):
            validator.validate(ambiguous, schema, schema_path)

    def test_schema_rejects_fixture_with_missing_required_field(self) -> None:
        schema_path = ROOT / "contracts/schemas/error.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        fixture = json.loads(
            (ROOT / "contracts/fixtures/errors/repetition-limit-exceeded.json").read_text(
                encoding="utf-8"
            )
        )
        broken = copy.deepcopy(fixture)
        broken.pop("request_id")
        with self.assertRaises(validator.ContractValidationError):
            validator.validate(broken, schema, schema_path)


if __name__ == "__main__":
    unittest.main()
