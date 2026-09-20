# Matches boundary

Owns Solo, Friendly and Party lifecycle; Room membership/Ready/host behavior;
participant snapshots; protected shared or per-solver Challenges; immutable
player Commit/setup timeout; Attempts; tie finalization; results; rematches;
idempotent services; and REST projections.

It calls the `games` registry for evaluation and creates durable events for the
`realtime` delivery boundary. It must not perform WebSocket I/O or embed
game-specific evaluator logic. Run `uv run pytest apps/matches/tests/` for its
focused suite; concurrency and protocol tests remain under root `tests/`.
