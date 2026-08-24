# Backend Handoff

This guide tells Backend developers and AI agents how to turn the product rules
and contracts into a maintainable Django system.

## Required context

Read game design, architecture overview/domain model, the protocol contract, and
the assigned AI task. Root and `apps/AGENTS.md` are binding.

## Target stack

T1 selected and locked this supported baseline:

- Python 3.12, Django 5.2 LTS and Django REST Framework 3.18
- ASGI + Django Channels 4.3
- PostgreSQL 17 source of truth
- Redis 7.4 channel layer/ephemeral coordination
- pytest/pytest-django, Ruff, mypy, coverage, pre-commit
- OpenAPI plus versioned JSON event schemas

`pyproject.toml`, `uv.lock` and ADR 0005 are canonical for exact versions and
upgrade policy.

## Module ownership

| Module | Owns |
| --- | --- |
| accounts | guest/user identity, profile snapshot, account upgrade |
| games | game definitions, RuleSet validation, secure generation ports, pure evaluators |
| matches | rooms, participants, challenges, attempts, lifecycle, result, use cases |
| realtime | consumers, subscriptions, event/snapshot delivery adapters |

Competition, progression, social, moderation, and analytics are added only by a
roadmap task. A conceptual boundary does not require a premature Django app.

## Write path: submit Guess

1. Authenticate viewer and validate the versioned command/idempotency identity.
2. Lock or atomically advance the participant Challenge state.
3. Verify membership, active state, deadline, and remaining Attempt capacity.
4. Ask the owning game adapter to validate/normalize Guess under frozen rules.
5. Access protected Secret through an explicit application port.
6. Call the pure evaluator.
7. Persist Attempt ordinal, Guess, Feedback, solved state, match transition, and
   durable outbox/event record in one transaction.
8. Commit, then publish viewer-specific events.
9. Return the original outcome for a valid retry.

Database constraints and transactions protect invariants. Redis locks alone are
not sufficient.

## Data rules

- Public identifiers are UUIDs and stable outside presentation/database order.
- Match stores an immutable RuleSet JSON snapshot plus schema and evaluator
  version; validation is game-aware.
- Secret storage is separate from general match projections and serializers.
- Attempts are immutable after acceptance.
- Lifecycle transitions occur through one explicit service/state machine.
- Store deadlines/timestamps in UTC; inject clocks/random sources into domain
  use cases for deterministic tests.

## API/realtime rules

- Serializers validate transport shape; use cases decide behavior.
- Consumers deliver/authorize and never calculate game outcomes.
- Publish only after commit, preferably through a transactional outbox once T4
  reliability requires it.
- Snapshot is viewer-specific recovery truth; events are incremental updates.
- Public/private event projections are distinct types/functions, not a flag on a
  generic serializer.

## Security defaults

- Environment-managed settings and credentials; secure production cookies/
  tokens, HTTPS/WSS, origin/host checks, throttles, request IDs.
- Redact secrets and private guesses in logs, traces, errors, admin lists, and
  analytics. Add regression tests for touched outputs.
- Join code is discovery, not ongoing authorization.
- Invalid Guess does not consume Attempt but may consume abuse quota.
- Do not reveal Secret for `voided` by default.

## Definition of done

For each task: migrations, tests, schemas/examples, admin/operational impact,
security review proportional to the change, successful quality commands, and
the root `AGENTS.md` handoff.
