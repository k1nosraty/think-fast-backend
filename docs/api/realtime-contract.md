# Frontend–Backend Contract Baseline

This document explains protocol principles, resources, events, errors, and
recovery. T0 is complete: the canonical machine-readable source is
`contracts/openapi.json`, its JSON Schemas, manifest, and fixtures at
`v1.0.0-draft.1`.

## Global rules

- HTTP base: `/api/v1/`; WebSocket: `/ws/v1/matches/{match_id}/`.
- Public IDs are UUIDs; timestamps are ISO-8601 UTC.
- Client sends intent, not authoritative state, rules, time, score, or attempt
  number.
- Commands have a stable command/idempotency identity where retries are valid.
- Semantic tokens are stable and unlocalized.
- Every representation is viewer-authorized; there is no "serialize whole
  Match" shortcut.
- Secrets and opponent-private Guess/Feedback are prohibited unless an explicit
  reveal policy authorizes them after terminal state.

## Frozen v1 draft HTTP surface

```text
POST /api/v1/guest-sessions/
GET  /api/v1/game-definitions/
POST /api/v1/solo-matches/
POST /api/v1/rooms/
POST /api/v1/rooms/{room_id}/join/
POST /api/v1/rooms/{room_id}/ready/
POST /api/v1/rooms/{room_id}/start/
POST /api/v1/matches/{match_id}/guesses/
POST /api/v1/matches/{match_id}/leave/
POST /api/v1/matches/{match_id}/rematch/
GET  /api/v1/matches/{match_id}/snapshot/
```

Compatible detail may be added during implementation. A rename, removal, or
semantic change requires explicit contract versioning and coordinated review.

## Command outcome

A successful Guess response contains:

- command ID and accepted Attempt ID/ordinal;
- semantic private feedback;
- solved state;
- current public match state;
- latest known event sequence.

It never returns the unrevealed Secret or another participant's private data.

## Feedback tagged union

Positional feedback:

```json
{
  "kind": "positional",
  "positions": ["exact", "present", "absent"]
}
```

Aggregate exact/present feedback:

```json
{
  "kind": "aggregate",
  "exact_count": 2,
  "present_count": 1
}
```

Permutation feedback:

```json
{
  "kind": "exact_count",
  "exact_count": 2
}
```

Clients must switch on `kind`; fields from one variant are not silently reused
for another.

## Event envelope

```json
{
  "type": "opponent.guessed",
  "version": 1,
  "match_id": "1d4a1b27-795b-4ddf-9c9b-b47ebf11b648",
  "sequence": 18,
  "occurred_at": "2026-08-23T12:30:00Z",
  "payload": {
    "participant_id": "85828209-75c5-426f-8d6f-f42af238b3da",
    "attempt_count": 4
  }
}
```

Candidate event types:

| Event | Visibility | Purpose |
| --- | --- | --- |
| `room.player_joined` | room public | lobby membership |
| `room.ready_changed` | room public | readiness |
| `match.countdown_started` | match public | synchronized start |
| `match.started` | match public | authoritative active state/deadline |
| `guess.evaluated` | participant private | accepted Attempt and Feedback |
| `opponent.guessed` | opponent public | pressure/progress without Guess |
| `participant.solved` | match public | solve status, not private history |
| `participant.disconnected` | match public | presence |
| `participant.reconnected` | match public | presence |
| `match.finished` | viewer-specific | result and authorized reveal |
| `rematch.requested` | room public | rematch readiness |
| `system.resync_required` | connection private | fetch snapshot after a gap |

Persisted match sequence is monotonic. Delivery may be duplicated or delayed;
clients ignore an already-applied sequence and fetch Snapshot on an unexplained
gap. Event delivery is not the source of truth.

## Snapshot contract

An authorized snapshot contains:

- match/room identity and current lifecycle state;
- immutable RuleSet snapshot including schema/evaluator version;
- server time, start time, and deadline;
- current viewer identity and permissions;
- viewer-visible participant/presence/progress state;
- viewer's permitted Attempt history and private feedback;
- terminal result and permitted reveal data;
- latest event sequence;
- `available_actions` for the viewer.

It must never contain another player's Guess/Feedback or an unrevealed Secret.
Initial load, page refresh, reconnect, and event-gap recovery all use Snapshot.

## Error envelope

```json
{
  "code": "duplicate_not_allowed",
  "message": "Repeated symbols are not allowed.",
  "field_errors": {"guess": ["duplicate_not_allowed"]},
  "request_id": "8e59db52-8767-4324-91a1-4592f240cfe8",
  "retryable": false
}
```

Initial stable codes include:

```text
invalid_guess_length
invalid_symbol
leading_zero_not_allowed
duplicate_not_allowed
repetition_limit_exceeded
match_not_active
deadline_elapsed
attempt_limit_reached
room_not_found
room_full
not_room_host
not_ready
idempotency_conflict
rate_limited
resync_required
client_version_unsupported
```

Human messages may be localized by clients. Behavior is based on `code`, not
message text.

## Authentication and authorization

- Guest creation returns a revocable identity credential suitable for the
  selected frontend platform.
- HTTP and WebSocket authenticate the same identity and enforce match membership.
- Room codes locate rooms but are not authorization after join.
- WebSocket subscription is denied before group membership when unauthorized.
- One primary gameplay connection per participant/match is the working default;
  T0 freezes replacement behavior.

## Contract workflow

1. Product behavior is decided in game design.
2. Frontend and Backend freeze schema/examples before parallel implementation.
3. Frontend develops against canonical fixtures/mock server.
4. Backend validates responses/events against the same schemas.
5. Shared contract/E2E tests gate integration.
6. Breaking changes require explicit versioning and both leads' approval.
