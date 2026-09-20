# ADR 0010 — Player-authored Challenge ownership and setup

**Status:** Accepted in T7 on 2026-08-26

## Decision

- A Room selects `challenge_source: system|players`; the default remains
  `system`. Player-authored setup is Friendly 1v1 only.
- A player-authored Match enters `setup`. Each participant creates exactly one
  immutable Challenge whose `creator` is themselves and whose `solver` is the
  other participant. Database constraints prevent duplicate solver assignments
  and self-solve.
- Secret validation uses the frozen game adapter before encrypted persistence.
  Raw Secret values never appear in snapshots, events, errors or analytics.
- Each successful Commit emits a creator-private acknowledgement and public
  count-only progress. The second Commit atomically schedules the shared
  countdown and deadline.
- Setup expires after 120 seconds. Timeout or leave cancels the Match, resets
  Room readiness and creates no Result, winner or loss.
- Normal terminal reveal is viewer-specific: a solver receives only the Secret
  assigned to that solver. Player-authored matches are Friendly-only and cannot
  be rating-eligible.

## Consequences

The former one-to-one shared Challenge becomes a collection. Existing system
matches retain one Challenge with no creator/solver; player-authored matches
retain two protected Challenges. Guess orchestration resolves the Challenge by
solver and falls back to the shared system Challenge.
