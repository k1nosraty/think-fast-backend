"""Base abstractions for game engines."""

from typing import Any, Protocol


class GameValidationError(ValueError):
    """Base exception for all game rule validation errors."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GameRules(Protocol):
    preset_id: str
    game_type: str
    match_mode: str
    schema_version: int
    evaluator_version: int
    sequence_length: int
    match_deadline_seconds: int
    attempt_limit: int

    def snapshot(self) -> dict[str, object]: ...


class GameAdapter(Protocol):
    def rules_from_snapshot(self, snapshot: dict[str, object]) -> Any: ...

    def generate_secret(self, rules: Any) -> object: ...

    def encode_secret(self, rules: Any, secret: object) -> str: ...

    def decode_secret(self, rules: Any, value: str) -> object: ...

    def evaluate(
        self, rules: Any, secret: object, guess: object
    ) -> tuple[object, dict[str, object], bool]: ...
