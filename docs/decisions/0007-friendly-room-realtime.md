# ADR 0007 — Friendly Room, tie finalization and realtime projection

**Status:** Accepted in T3; reliability addendum accepted in T4 on 2026-08-24

## Decision

- `Room` is a reusable lobby and never stores Attempts or Secret. `Match` is a
  separate immutable competitive instance with frozen Participant snapshots.
- A Room has exactly two active members for Social MVP. Row locking protects
  join/start; membership constraints prevent duplication; joining resets Ready.
- Host ownership transfers to the oldest remaining member before a Match. Late
  join is rejected after start.
- Friendly start uses a server-owned three-second countdown. Test settings use
  zero seconds. Activation is idempotent and converges through the realtime
  connection or the next authorized HTTP command/Snapshot.
- Both Participants reference one encrypted Challenge and retain independent
  Attempts. The first solve opens the frozen 500 ms tie window. A second equal-
  Attempt solve inside it produces a draw; otherwise fewer Attempts then earlier
  server solve time determines the winner.
- Match events are persisted with monotonic sequence before publication.
  `transaction.on_commit` sends only an event ID to Channels; each consumer
  reloads and authorizes its projection. Private `guess.evaluated` reaches only
  its Participant; opponents receive `opponent.guessed` without Guess/Feedback.
- WebSocket authenticates the same Guest token through an Authorization header
  or browser subprotocol. Query-string tokens are intentionally unsupported so
  credentials do not enter URL logs or browsing history.

## T4 reliability addendum

- Event delivery is an at-least-once transactional outbox. A successful database
  commit remains authoritative during Redis failure; retry metadata is durable.
- One gameplay connection is primary. A new connection replaces the old one;
  stale disconnect callbacks cannot disconnect the replacement.
- Disconnect starts a configurable 30-second grace without pausing the deadline.
  Reconnect clears it; durable expiry abandons without revealing the Secret.
- Clients ignore duplicate sequences, request ordered authorized replay for
  gaps, and fetch Snapshot when `system.resync_required` is returned.
- A periodic database-backed sweep converges countdown, tie/deadline, grace and
  pending delivery state after process restart.
