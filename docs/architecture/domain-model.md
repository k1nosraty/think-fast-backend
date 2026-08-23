# Domain Model

This is a conceptual model, not a committed database schema.

## Main aggregates

### GameDefinition

Versioned reusable template containing Game Type identifier, allowed configuration
schema, defaults, and availability. Existing matches retain their frozen rule
snapshot when a definition changes.

### Room

Pre-match multiplayer boundary: join code, host, visibility, capacity, members,
and readiness. A room can create a match but is not the match itself.

### Match

Authoritative lifecycle, frozen versioned RuleSet snapshot, participant set,
timing, win policy, and terminal outcome. A Match owns one or more Challenges.

### Participant

Stable membership linking a guest or registered user to a match. Owns status,
display snapshot, permissions, and final placement.

### Challenge

One protected target assigned to one or more solvers. It references Secret
material, start/deadline, state, reveal policy, optional creator, and solvers.
Player-authored duels create one Challenge per solver while a shared race uses
one Challenge for every participant. `Challenge` prevents a false assumption
that every Match has one global Secret.

### Attempt

Immutable accepted Guess with participant, Challenge, normalized sequence, ordinal,
server timestamp, semantic feedback, and solved flag. Invalid commands are not
attempts but may be captured in security telemetry.

### MatchEvent

Versioned, ordered fact used for realtime delivery and recovery. Payloads are
authorization-aware; private feedback is not broadcast to opponents unless the
rules explicitly allow it.

## Value objects

- `GameType`: `number`, `color`, later `word`
- `MatchMode`: `practice`, `friendly`, later `ranked`
- `RuleSetSnapshot`: immutable validated game/competition settings with schema
  and evaluator version
- `SymbolId`: locale-neutral digit/color identity
- `Guess`: ordered normalized symbol tuple
- `Feedback`: mode-specific semantic result
- `HistoryPolicy`: `full`, `last_n(N)`, `none`
- `WinPolicy`: ranking/tie strategy

## Invariants

- Rules and participants cannot change after match activation.
- Only active, eligible participants may submit guesses.
- Attempt ordinal is monotonic per participant Challenge.
- A command idempotency key maps to at most one accepted attempt.
- Terminal Challenges and Matches accept no new Attempts.
- Secret access is never part of a general match serializer.
- Game evaluators are deterministic for `(rules, secret, guess)`.
