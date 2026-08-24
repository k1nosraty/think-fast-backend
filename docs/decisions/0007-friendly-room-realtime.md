# ADR 0007 — Friendly Room, tie finalization and realtime projection

**Status:** Accepted in T3 on 2026-08-24

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

## Consequences

T3 provides ordered persisted events and safe post-commit fan-out, but not the
durable outbox retry, event-gap protocol, connection replacement, disconnect
grace, Redis disruption recovery or process-restart proofs owned by T4.
