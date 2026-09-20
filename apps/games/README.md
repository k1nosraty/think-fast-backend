# Games boundary

Owns versioned Number and Color presets, palette metadata, validation,
injectable secure generation and pure evaluators. Word remains a bounded spike
with placeholder lexicon data, not a released game mode. `registry.py` is the
narrow explicit adapter map used by Match orchestration; do not replace it with
a generic plugin framework. See `apps/AGENTS.md` for scope rules. This app has
no ORM models and must remain testable without Django setup.

Run `uv run pytest apps/games/tests/` for focused evaluator coverage.
