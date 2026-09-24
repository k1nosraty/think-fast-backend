# Frontend–Backend Contract Baseline

This document explains protocol principles, resources, events, errors, and
recovery. T0 is complete: the canonical machine-readable source is
`contracts/openapi.json`, its JSON Schemas, manifest, and fixtures at
`v1.0.0-draft.1`. The current compatible bundle revision is
`v1.0.0-draft.1-r5`; `contracts/manifest.json` records that revision, every
canonical fixture, and the deterministic SHA-256 of all other JSON artifacts.

## Global rules

- HTTP base: `/api/v1/`; WebSockets: `/ws/v1/rooms/{room_id}/` for lobby
  updates and `/ws/v1/matches/{match_id}/` for gameplay.
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
GET  /api/v1/rooms/by-code/{join_code}/
GET  /api/v1/rooms/{room_id}/
POST /api/v1/rooms/{room_id}/join/
POST /api/v1/rooms/{room_id}/kick/
POST /api/v1/rooms/{room_id}/leave/
POST /api/v1/rooms/{room_id}/ready/
POST /api/v1/rooms/{room_id}/rules/
POST /api/v1/rooms/{room_id}/start/
POST /api/v1/matches/{match_id}/challenges/
POST /api/v1/matches/{match_id}/guesses/
POST /api/v1/matches/{match_id}/leave/
POST /api/v1/matches/{match_id}/next-round/
POST /api/v1/matches/{match_id}/rematch/
GET  /api/v1/matches/{match_id}/snapshot/
```

The Account verification/session endpoints previously present only in the
Frontend copy are not part of this revision because no Backend route implements
them. Adding them requires a separate approved contract and implementation.

Compatible additions increment the bundle revision (`-rN`) while keeping the
contract version. A rename, removal, newly required field, narrowed accepted
value, or semantic change requires a new incompatible contract version and
coordinated client/server review. Every revision regenerates the manifest
checksum and is copied from Backend to consumers; generated copies are never
edited by hand.

## Party contract

`POST /rooms/` accepts `room_mode: party` with `rounds_count` restricted to
3, 5 or 7 (any other Party value is a 400); omitting them preserves the `duel`
and 5-round defaults. Duel ignores `rounds_count` and always plays one round.
A Duel room holds exactly two members. A Party room holds three to eight members: one Creator plus
at least two Guessers, which is the minimum for placement scoring (1st/2nd/3rd)
to be meaningful. `Room.minimum_members()`/`Room.maximum_members()` are the
authoritative capacity policy; the start, join and rematch paths all read it
rather than re-deriving the numbers. Room snapshots expose `minimum_members`,
`maximum_members` and `allowed_rounds_count` (`Room.allowed_rounds()`:
`[1]` for Duel, `[3, 5, 7]` for Party), so clients derive the lobby gate and
the offered round choices from the server instead of mirroring constants.

A Party match snapshot uses the common Snapshot schema plus `round_number`,
`total_rounds`, `creator_participant_id`, per-participant `score`, `round_score`,
`round_rank` and `is_creator`, the `scores` map, and `round_state`. Only the
current creator may commit the round challenge; non-creators may submit guesses.
After `round.finished`, `next_round` appears in `available_actions` while another
round remains. `POST /matches/{match_id}/next-round/` accepts the common
`command_id` body, advances to the next round or returns the terminal match
snapshot, and is retry-safe for the same participant and command identity. A
Party Match that can no longer field the minimum number of active players is
terminated with `Result.reason = not_enough_players`.

Party events use the common ordered envelope. The canonical
`party-round-finished.json` fixture freezes the public round summary, revealed
round secret and score map; participant-private `guess.evaluated` and public
`opponent.guessed` may additionally carry `round_number`.

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

Number Guess remains a fixed-width digit string. Color Guess is an ordered JSON
array of stable `color_id` values. Color Classic uses positional or aggregate
feedback according to its frozen RuleSet; Color Permutation exposes only
`exact_count`. Palette definitions in the RuleSet include hex, localization
key, shape and pattern, and clients must not communicate meaning by color alone.

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
| `challenge.setup_started` | match public | setup expiry and required count |
| `challenge.committed` | creator private | idempotent Commit acknowledgement |
| `challenge.setup_progress` | match public | count-only setup progress |
| `challenge.setup_cancelled` | match public | timeout/leave cancellation, no Result |
| `match.countdown_started` | match public | synchronized start |
| `match.started` | match public | authoritative active state/deadline |
| `guess.evaluated` | participant private | accepted Attempt and Feedback |
| `opponent.guessed` | opponent public | pressure/progress without Guess |
| `participant.solved` | match public | solve status, not private history; carries `participant_id` and `attempt_count`, plus `display_name`, `solve_duration_ms` and `round_number` in Party |
| `participant.disconnected` | match public | presence |
| `participant.reconnected` | match public | presence |
| `creator.selected` | match public | first-round Creator announcement |
| `creator.rotated` | match public | Creator hand-over for a new round or after a Creator leaves |
| `round.created` | match public | new Party round identity, Creator and setup expiry |
| `round.started` | match public | authoritative round start and deadline |
| `round.finished` | match public | public round summary: ranked solvers, Creator score, revealed secret and score map |
| `scores.updated` | match public | per-participant total score map for the round |
| `match.finished` | viewer-specific | result and authorized reveal |
| `rematch.requested` | room public | pending proposal and expiry |
| `rematch.accepted` | room public | new Match identity |
| `rematch.declined` | room public | explicit decline/cancel |
| `rematch.expired` | room public | proposal timeout |
| `system.resync_required` | connection private | fetch snapshot after a gap |

Persisted match sequence is monotonic. Delivery may be duplicated or delayed;
clients ignore an already-applied sequence and fetch Snapshot on an unexplained
gap. Event delivery is not the source of truth.

For a recoverable gap, an authorized client may first send:

```json
{"type": "resync", "last_sequence": 17}
```

The server replays all viewer-authorized stored events after sequence 17 in
order. A duplicate is ignored client-side. An invalid cursor returns
`system.resync_required`; a missing/pruned history in a future retention policy
must do the same, and the client then fetches Snapshot. Reconnect never pauses
the persisted deadline.

Room events use `room_id` and a monotonic sequence scoped to the Room. Match
events use `match_id` and a monotonic sequence scoped to the Match. They never
share one sequence space.

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

## Rematch contract

`POST /matches/{match_id}/rematch/` accepts a command ID and optional
`action: request|decline` (`request` by default). The first request opens a
60-second proposal; the other participant's request accepts it. The Room
snapshot exposes `latest_match_id` plus proposal state, requester, expiry and
the new Match ID. Clients then subscribe to/fetch the new Match normally.

## Player-authored Challenge contract

A Room may opt into `challenge_source: players` (default `system`). Starting it
creates a Friendly-only Match in `setup`. Each participant calls
`POST /matches/{match_id}/challenges/` once with `command_id` and a RuleSet-shaped
`secret`; the server validates, encrypts and assigns it to the other solver.
Snapshot exposes only expiry, own Commit status and aggregate Commit count.
Neither Secret, target solver nor opponent-private acknowledgement is public.
The second Commit schedules countdown. Setup expiry/leave produces `cancelled`
with `result: null` and no rating eligibility. Normal finish reveals only the
Challenge assigned to the current viewer.

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
authentication_required
permission_denied
match_not_found
invalid_request
invalid_guess_length
invalid_symbol
leading_zero_not_allowed
duplicate_not_allowed
repetition_limit_exceeded
invalid_permutation
match_not_active
deadline_elapsed
attempt_limit_reached
room_not_found
room_full
not_room_host
not_ready
idempotency_conflict
challenge_setup_closed
challenge_setup_expired
challenge_already_committed
challenge_not_committed
feature_disabled
internal_error
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
- One primary gameplay connection exists per participant/match. A newer socket
  atomically replaces and closes the older socket. Disconnect starts the
  configured 30-second grace while the match timer continues; reconnect clears
  it, and expiry durably abandons the participant/match without revealing the
  secret.

## Contract workflow

1. Product behavior is decided in game design.
2. Frontend and Backend freeze schema/examples before parallel implementation.
3. Frontend develops against canonical fixtures/mock server.
4. Backend validates responses/events against the same schemas.
5. Shared contract/E2E tests gate integration.
6. Breaking changes require explicit versioning and both leads' approval.
