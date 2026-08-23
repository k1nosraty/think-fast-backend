# Quality and Acceptance Strategy

Quality follows risk and vertical behavior; raw coverage percentage is not a
substitute for invariants.

## Test layers

| Layer | Purpose |
| --- | --- |
| Pure unit | RuleSet validation and evaluator example/edge matrix |
| Domain/application | lifecycle, authorization, timing, idempotency, result |
| Persistence/integration | constraints, transactions, locking, outbox |
| Contract | HTTP/event/snapshot/error examples validate shared schemas |
| End-to-end/API | real guest-to-result and reconnect/rematch backend flows |
| Load/resilience | fan-out, Guess spikes, reconnect storms, dependency failure |

## Mandatory risk matrix

Relevant tasks must cover:

- invalid length/symbol/duplicate/repetition rules;
- duplicate-safe feedback consumption;
- intentional repeated Guess versus retransmitted command;
- unauthorized room/match/event/snapshot access;
- Guess at deadline and after terminal state;
- simultaneous valid guesses and near-simultaneous solves;
- refresh/reconnect, duplicate event, event gap, and replaced connection;
- Redis loss/restart without divergent PostgreSQL result;
- no Secret/private Guess leakage through response, event, snapshot, error, log,
  analytics, or admin projection.

## Vertical acceptance

Given/When/Then scenarios and canonical JSON fixtures are frozen in T0 and grow
with each task. Backend schema tests validate the exact fixtures distributed to
the separate Frontend repository.

Example:

```gherkin
Given an active Number match whose rules forbid repeated digits
When the participant submits "11234"
Then the command fails with "duplicate_not_allowed"
And no Attempt is created
And opponent progress does not change
```

## Task validation

An AI agent must discover and run the repository's actual commands, not invent
passing output. Minimum gates after T1 are expected to include formatting/lint,
type checks, Django checks, migration consistency, unit/integration tests, and
contract validation. Tasks touching realtime/concurrency add their dedicated
suites. T8 adds security, load, backup/restore, and staging smoke checks.

## Playtest gates

Gameplay parameters are evidence-driven. Record anonymized aggregate outcomes
by exact RuleSet version: completion, solve time, Attempts, abandonment,
rematch, and invalid/spam rate. Never send raw Secret/private Guess to general
analytics.
