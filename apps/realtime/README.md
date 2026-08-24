# Realtime boundary

T4 exposes authenticated Room/Match sockets with strict viewer projections,
one primary gameplay connection, 30-second disconnect grace, ordered replay,
and durable post-commit delivery. PostgreSQL events are authoritative; Redis
delivery is at-least-once and disposable.

Clients apply only the next sequence, ignore duplicates, and send a `resync`
command with their last applied sequence after a gap. Invalid cursors require a
fresh authorized HTTP Snapshot. Run `sweep_reliability` periodically so pending
deadlines, grace expiries, and outbox rows converge after process restarts.
