# AGENTS.md — Think Fast Project Contract

This file is the primary instruction contract for AI agents. It applies to the
entire repository. A nested `AGENTS.md` adds local rules but cannot weaken these
rules.

## Mandatory reading order

Before any implementation task, read once:

1. `README.md`
2. `ROADMAP.md`
3. `docs/product/game-design.md`
4. `docs/architecture/overview.md`
5. `docs/api/realtime-contract.md`
6. the assigned task in `docs/execution/BACKEND-TASKS.md`
7. every nearer `AGENTS.md` for files being changed

Read ADRs only when the task touches their decision. Do not repeatedly load
unrelated documentation.

## Task protocol

1. Confirm the requested task ID and work only on that task.
2. Inspect current code/tests before proposing changes; preserve valid work.
3. State assumptions only when the documents do not decide the matter.
4. If an unresolved choice changes fairness, public contracts, persistence,
   security, privacy, or scope, stop and ask. Do not silently invent it.
5. Implement the smallest coherent vertical solution satisfying acceptance
   criteria. Do not start later roadmap tasks.
6. Run the task's tests plus relevant regression checks.
7. Update the source-of-truth document when behavior or contracts change.
8. Handoff with changed files, decisions, migrations, commands/tests run,
   results, known limitations, and the next task ID. Never claim unrun checks.

## Product invariants

- The server is authoritative for rules, secrets, clock/deadlines, accepted
  attempts, feedback, scoring, eligibility, and terminal results.
- A `Room` is a reusable social/lobby container; a `Match` is one immutable
  competitive instance. Never merge them.
- `GameType` says what is solved; `MatchMode` says how players compete;
  `RuleSet` contains machine rules; `Preset` is a user-facing named RuleSet.
- Every active match owns an immutable, versioned RuleSet snapshot.
- A request that fails validation is not an Attempt. A retransmitted command
  with the same idempotency identity must not create another Attempt.
- Raw secrets and private guesses never appear in public events, opponent
  snapshots, normal logs, analytics, or generic serializers.
- Color is never the only carrier of meaning.

## Architecture constraints

- Use a modular Django monolith. Do not introduce microservices, Kafka,
  Kubernetes, full event sourcing, or a generic plugin framework without a new
  accepted ADR.
- Keep game evaluation pure Python and deterministic for
  `(rules, secret, guess)`; no ORM, transport, clock, randomness, cache, or I/O.
- Match orchestration must not contain growing `if game_type == ...` branches.
  Use a small explicit evaluator registry and a narrow game contract.
- Do not build a `UniversalGameEngine`. Share lifecycle concepts, not arbitrary
  game-specific fields.
- PostgreSQL decides durable state. Redis is disposable acceleration/delivery.
- Publish realtime outcomes only after the authoritative transaction commits.
- Use stable UUIDs in public contracts and stable semantic tokens in payloads.
- HTTP and WebSocket schemas are versioned. Breaking changes require explicit
  versioning and coordinated frontend/backend approval.
- Avoid `player1`/`player2` domain fields; model participants as a collection.
  Do not implement Teams until a roadmap task requests them.

## Implementation quality

- Prefer application services/use cases for writes and transaction boundaries.
- Protect concurrency with constraints plus locking/atomic state transitions;
  in-memory checks alone are insufficient.
- Add migrations for model changes and never rewrite an applied migration.
- Keep dependencies pinned and justified. Do not add a package for trivial code.
- Use environment configuration; never commit credentials or production secrets.
- Public errors use stable machine codes. Frontend behavior must not parse human
  error messages.
- Add tests for normal, boundary, invalid, unauthorized, retry, concurrency,
  timeout, reconnect, and secret-leakage behavior as applicable.

## Scope guardrails

Unless the assigned task explicitly says otherwise, do not implement:

- Word, player-authored duels, ranked matchmaking/rating, teams, tournaments,
  spectators, chat, friends, avatar upload, payments, ads, or AI validation;
- abstractions designed only for hypothetical games;
- frontend implementation, React tooling, UI components, or client state inside
  this backend repository.

Future work may be documented without prebuilding its database tables or APIs.

## Required final report

Use this compact format:

```text
Task: Tn — name
Outcome: what now works
Changed: important files/components
Decisions: new or confirmed decisions
Migrations: names or none
Validation: exact commands and pass/fail totals
Limitations: remaining known gaps
Next: next roadmap task, without starting it
```
