# Phase 0 Decision Register

- Status: **Accepted baseline for Backend T1/T2**
- Date: 2026-08-24
- Contract version: `v1.0.0-draft.1`
- Owner: Product owns gameplay; Backend owns canonical machine contracts;
  breaking changes require Product plus affected client/server leads.

These decisions freeze the first Backend implementation. Values may change only
through a recorded, versioned decision and compatible contract/preset update.

## MVP and delivery

| Decision | Accepted value |
| --- | --- |
| First Game Type | Number |
| Match modes | Solo practice, then private Friendly 1v1 |
| Friendly challenge | Same server-generated Secret for both players |
| Room capacity | Exactly two active players in Social MVP |
| History | Full accepted Guess history visible to its owner |
| Later | Color, player-authored Challenge, Word, Ranked, team/tournament |

## Number presets

All values are fixed-width strings over ASCII digits `0..9`.

| Field | Classic 5 | Brain Burner 6 |
| --- | ---: | ---: |
| Preset ID | `number_classic_5_v1` | `number_brain_burner_6_v1` |
| Length | 5 | 6 |
| Leading zero | No | No |
| Duplicates | Yes | Yes |
| Maximum occurrences per digit | 2 | 2 |
| Feedback | Positional | Positional |
| History | Full | Full |
| Match deadline | 180 seconds | 240 seconds |
| Attempt limit | 12 | 15 |

Rationale: duplicates prevent the two-probe `12345`/`67890` strategy from
collapsing the search space too easily. A repetition cap of two preserves
difficulty without making early play unnecessarily opaque. Full history keeps
the game deductive rather than memory-dependent. Unrestricted repetition is an
experiment, not an official MVP preset.

## Feedback and Guess behavior

- Positional semantic tokens are `exact`, `present`, `absent`.
- Evaluation consumes Exact matches first, then remaining symbol inventory.
- Invalid Guess consumes no Attempt but may consume throttle/abuse quota.
- Intentionally resubmitting the same valid Guess creates another Attempt.
- Replaying the same command ID returns the original outcome and creates no new
  Attempt.
- Public/opponent payloads never include actual Guess or Feedback.

Canonical duplicate examples live in
`contracts/fixtures/number-feedback-cases.json` and are part of the contract.

## Timing, result, and reveal

| Decision | Accepted value |
| --- | --- |
| Clock | Server authoritative, UTC |
| Win ordering | Solved, fewer Attempts, lower server solve duration |
| Tie window | 500 milliseconds when Attempts are equal |
| No solver by limit/deadline | `unsolved`/draw; no closest-Guess winner |
| Multiplayer disconnect | Timer continues |
| Friendly reconnect grace | 30 seconds |
| Connection replacement | New authenticated connection becomes primary |
| Reveal on normal solved/unsolved finish | Yes, to participants |
| Reveal on abandoned/voided/cancelled | No by default |

These values are versioned preset/competition policy, not hardcoded UI behavior.

## Identity and access

- Guest may play Solo and create/join private Friendly rooms.
- MVP gameplay does not require a registered account.
- Guest identity lifetime is 30 days from last activity; upgrade-to-account is a
  later capability and must preserve explicit ownership rules.
- Market baseline is Persian-first/Iran with locale-neutral API values. A future
  registered-account flow will prefer mobile OTP, but T1/T2 must not implement
  OTP without a dedicated task/vendor/security decision.
- Join code discovers a Room; authenticated membership authorizes later access.

## Retention and privacy baseline

| Data | Baseline |
| --- | --- |
| Match summary/result | 365 days for MVP evaluation |
| Accepted Attempts/private Feedback | 90 days |
| Guest identity/session metadata | 30 days after last activity |
| Protected Secret | Delete or cryptographically make inaccessible within 24 hours after terminal Match, unless a documented security incident hold applies |
| Operational logs | 30 days, secret/private-Guess redacted |
| Aggregate analytics | May persist without raw Secret or private Guess |

Production legal/privacy review in T8 may shorten these periods. It must not
silently lengthen sensitive-data retention.

## Initial capacity target

T8 must validate at least:

- 2,000 concurrent WebSocket connections;
- 1,000 concurrently active Friendly matches;
- 100 accepted Guess commands/second sustained for five minutes;
- a burst of 300 Guess commands/second for 30 seconds;
- 95th-percentile accepted Guess response under 300 ms in the agreed staging
  topology, excluding client network latency;
- reconnect storm of 1,000 clients over 60 seconds without divergent state.

These are engineering test targets, not a public SLO. T1 must avoid architecture
that prevents horizontal ASGI scaling, but must not prematurely optimize.

## Contract and compatibility

- HTTP base is `/api/v1/`; realtime endpoint is
  `/ws/v1/matches/{match_id}/`.
- Public identifiers are UUIDs; timestamps are ISO-8601 UTC.
- Snapshot is recovery truth; events are ordered incremental updates.
- Event sequence is monotonic per Match. Duplicate events are allowed in
  delivery; unexplained gaps require Snapshot resync.
- Backend repository owns `contracts/openapi.json`, JSON Schemas, manifest, and
  canonical fixtures. Frontend consumes a pinned copy/generated types.
- `v1.0.0-draft.1` may receive compatible additions during implementation.
  Renames/removals/meaning changes require a new incompatible contract version.

## Explicitly not decided by T0

Dependency/tool versions, settings layout, database configuration, and CI are
T1 decisions. Database tables/models, evaluator code, endpoints, and WebSocket
consumers start in T2/T3. T0 contains no gameplay implementation.
