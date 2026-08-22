# API and Realtime Contract Direction

This document defines protocol principles and candidate resources. Exact paths
and payload schemas are finalized with the first vertical slice.

## Versioning

- HTTP prefix: `/api/v1/`
- WebSocket endpoint: `/ws/v1/matches/{match_id}/`
- Every event carries `type`, `version`, `match_id`, `sequence`, and `occurred_at`.
- Public identifiers are UUIDs. Enum values are stable machine tokens.

## Candidate HTTP resources

```text
POST /api/v1/guest-sessions/
GET  /api/v1/game-definitions/
POST /api/v1/solo-matches/
POST /api/v1/rooms/
POST /api/v1/rooms/{room_id}/join/
POST /api/v1/rooms/{room_id}/ready/
POST /api/v1/rooms/{room_id}/start/
GET  /api/v1/matches/{match_id}/
POST /api/v1/matches/{match_id}/guesses/
GET  /api/v1/matches/{match_id}/snapshot/
```

Guess submission includes an `Idempotency-Key` header or explicit command ID.
The response contains semantic feedback visible to that participant and the
latest match event sequence. It never contains the unrevealed secret.

## Candidate WebSocket events

- `room.member_joined`
- `room.member_left`
- `room.readiness_changed`
- `match.started`
- `attempt.accepted` (private detail; public projection may contain only progress)
- `participant.solved`
- `match.completed`
- `match.cancelled`
- `system.resync_required`

## Snapshot and reconnect

WebSockets are a notification stream, not the sole state store. On connect or a
sequence gap, the client obtains an authorized snapshot containing current
rules, public participant state, its own allowed attempt history, match status,
deadline, and latest sequence.

## Error shape

Errors should use a stable machine code, human-readable message, optional field
details, request correlation ID, and retryability metadata. Examples include
`invalid_guess_length`, `symbol_not_allowed`, `match_not_active`,
`deadline_elapsed`, and `idempotency_conflict`.

## Visibility

Each representation is built for one viewer role. Private guesses and feedback
must not leak through room broadcasts, opponent snapshots, admin lists, logs,
or generic model serializers.
