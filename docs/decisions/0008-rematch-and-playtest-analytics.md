# ADR 0008 — Rematch lifecycle and playtest analytics

**Status:** Accepted in T5 on 2026-08-24

## Decision

- A rematch always remains inside the existing Room and creates a new immutable
  Match, Participant set, RuleSet snapshot, Challenge, Secret and event sequence.
- `action=request` is the compatible default. The first participant opens a
  60-second proposal; a request from the other participant accepts it.
  `action=decline` explicitly declines/cancels it. Expired or declined proposals
  may be requested again while the source Match is still the Room's latest.
- Rematch commands are durable and idempotent. Only members of the terminal
  source Match may act, and an old Match cannot start another rematch after a
  newer Match exists.
- Playtest analytics is a write-only allowlisted port. It stores aggregate
  lifecycle/rules metadata but never Secret, Guess, Feedback, token, identity,
  network metadata or arbitrary payloads.
- Preset balance remains versioned. A playtest may recommend a new preset, but
  must not mutate the rules snapshot of any existing Match.

## Consequences

Clients can complete play → result → rematch without recreating the Room.
Exports are aggregate and safe to share with the product team. Retention,
warehouse integration and production dashboards remain T8 concerns.
