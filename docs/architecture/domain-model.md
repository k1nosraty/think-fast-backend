# Domain Model

This is a conceptual model, not a committed database schema.

## Main aggregates

### GameDefinition

Versioned reusable template containing mode identifier, allowed configuration
schema, defaults, and availability. Existing matches retain their frozen rule
snapshot when a definition changes.

### Room

Pre-match multiplayer boundary: join code, host, visibility, capacity, members,
and readiness. A room can create a match but is not the match itself.

### Match

Authoritative lifecycle, frozen rule configuration, participant set, timing,
ranking policy, and terminal outcome. A match contains one or more rounds.

### Participant

Stable membership linking a guest or registered user to a match. Owns status,
display snapshot, permissions, and final placement.

### Round

One secret challenge. References protected secret material, start/deadline,
state, and reveal policy. Player-authored duels can create one target round per
solver while shared races use one shared target.

### Attempt

Immutable accepted guess with participant, round, normalized sequence, ordinal,
server timestamp, semantic feedback, and solved flag. Invalid commands are not
attempts but may be captured in security telemetry.

### MatchEvent

Versioned, ordered fact used for realtime delivery and recovery. Payloads are
authorization-aware; private feedback is not broadcast to opponents unless the
rules explicitly allow it.

## Value objects

- `ModeId`: `number_code`, `hidden_color_code`, `color_permutation`
- `RuleConfig`: immutable validated per-mode settings
- `SymbolId`: locale-neutral digit/color identity
- `Guess`: ordered normalized symbol tuple
- `Feedback`: mode-specific semantic result
- `HistoryPolicy`: `full`, `latest_only`, `none`
- `WinPolicy`: ranking/tie strategy

## Invariants

- Rules and participants cannot change after match activation.
- Only active, eligible participants may submit guesses.
- Attempt ordinal is monotonic per participant round.
- A command idempotency key maps to at most one accepted attempt.
- Terminal rounds and matches accept no new attempts.
- Secret access is never part of a general match serializer.
- Mode evaluators are deterministic for `(rules, secret, guess)`.
