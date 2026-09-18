# Realtime boundary

T4 exposes authenticated Room/Match sockets with strict viewer projections,
one primary gameplay connection, 30-second disconnect grace, ordered replay,
and durable post-commit delivery. PostgreSQL events are authoritative; Redis
delivery is at-least-once and disposable.

Clients apply only the next sequence, ignore duplicates, and send a `resync`
command with their last applied sequence after a gap. Invalid cursors require a
fresh authorized HTTP Snapshot. Run `sweep_reliability` periodically so pending
deadlines, grace/rematch expiries, and outbox rows converge after process restarts.

Local development uses Redis from `compose.yaml`; tests use the test settings'
in-memory channel layer unless a dedicated PostgreSQL/Redis test explicitly
requires real dependencies. Useful operations are:

```bash
uv run python manage.py publish_outbox --limit 100
uv run python manage.py sweep_reliability --limit 100
uv run pytest apps/realtime/tests/ tests/realtime/
```
