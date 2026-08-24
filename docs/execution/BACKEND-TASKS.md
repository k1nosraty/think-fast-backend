# Backend AI Execution Tasks

This is the canonical Django work plan. Give an AI agent exactly one task with
the current repository. The separate React repository has its own task plan.

## Prompt prefix for every task

> Continue on the current Think Fast Backend repository. Read and obey root
> `AGENTS.md`, every nearer `AGENTS.md`, the mandatory documents it names, and
> only the assigned task below. Preserve valid existing and unrelated user work.
> Do not implement React/frontend code and do not start later tasks. If an
> unresolved choice changes fairness, public contracts, persistence, security,
> privacy, or scope, stop and ask. Complete the task with migrations, tests,
> schema/docs updates and the exact handoff required by `AGENTS.md`. Report only
> checks actually run.

## T0 — Freeze backend-facing decisions and contracts

**Effort:** High. **Code:** contracts/tooling only; no gameplay implementation.

**Status:** Complete on 2026-08-24. Do not rerun or reinterpret it implicitly;
use the decision register and versioned contracts.

- Record final Phase 0 choices from Product/Frontend/Backend: Number rules,
  history, timer/attempt, win/tie/reveal, guest/auth, retention, capacity.
- Freeze OpenAPI plus versioned event/error/snapshot schemas and canonical JSON
  fixtures for Solo and planned Friendly 1v1.
- Add automatic schema/example validation used in CI.
- Record ownership: Backend is canonical schema owner; breaking changes require
  coordinated approval and explicit versioning.

**Accept:** no hidden T1/T2 decision; duplicate-feedback matrix approved; every
example validates; no endpoint, model, evaluator, or consumer implemented.

## T1 — Django engineering foundation

**Effort:** High.

**Status:** Complete on 2026-08-24. The next implementation task is T2; do not
reinterpret or expand this foundation implicitly.

- Verify and pin supported Python/Django/DRF/Channels/PostgreSQL/Redis versions.
- Replace scaffold dependencies with the selected `pyproject.toml`/lock flow.
- Configure Ruff, mypy, pytest, coverage, pre-commit and CI.
- Split environment settings; remove tracked secrets; add `.env.example`.
- Add PostgreSQL/Redis local stack, health/readiness skeleton, structured
  redacted request logging, repeatable bootstrap/check commands.
- Scaffold only `accounts`, `games`, `matches`, `realtime` boundaries and local
  tests/READMEs. Add custom User only if T0 requires it now.

**Accept:** clean bootstrap on a new machine; production refuses insecure config;
format/lint/types/Django/migrations/tests/contracts pass; no gameplay exists.

## T2 — Solo Number vertical slice

**Effort:** Very high.

**Status:** Complete on 2026-08-24. Solo Number is the only implemented gameplay
flow. The next task is T3; do not add room/realtime behavior implicitly.

- Implement immutable validated RuleSet snapshot with schema/evaluator version.
- Implement secure injectable Secret generator and pure duplicate-safe evaluator.
- Implement minimum guest identity, Match, Participant, Challenge/protected
  Secret, Attempt, Result, lifecycle and application services.
- Implement create/start/submit Guess/snapshot/finish/abandon REST behavior,
  idempotency, permissions, throttles, stable errors and safe admin projections.
- Conform exactly to T0 OpenAPI/fixtures; add seed/demo utility.
- Test edge matrix, unauthorized access, timeout, retry, transaction and leakage.

**Accept:** a guest completes Solo through public API; invalid Guess creates no
Attempt, intentional repeat does, retry does not; refresh Snapshot is correct;
Secret never leaks before authorized reveal; all gates pass.

## T3 — Private room and realtime shared-secret 1v1

**Effort:** Very high.

**Status:** Complete on 2026-08-24. Private Friendly 1v1 is implemented; the
next task is T4 reliability/recovery and must not be folded back into T3.

- Implement Room separate from Match: join code, host/transfer, capacity,
  membership, Ready reset, start permission, participant freeze, late-join deny.
- Create one shared Challenge with independent participant Attempts.
- Implement Channels authentication/subscriptions, ordered versioned viewer-
  specific events, public/private projections, presence, countdown and result.
- Publish only after authoritative transaction commit.
- Test cross-room isolation, unauthorized subscription, host leave, room full,
  simultaneous play/finish, event visibility, errors and leakage.

**Accept:** two independent guests complete 1v1 through REST/WebSocket; outcome
is deterministic under near-simultaneous wins; no unauthorized/private payload
crosses participants; schemas/fixtures stay current.

## T4 — Reliability and recovery

**Effort:** Very high.

**Status:** Complete on 2026-08-24. Durable outbox delivery, gameplay connection
replacement, grace/abandonment, ordered resync and restart convergence are
implemented. The next task is T5; do not add rematch/analytics implicitly.

- Audit every mutation for database constraint, atomic transition/locking,
  idempotency lifetime/conflict and post-commit publication.
- Add transactional outbox/durable ordered delivery where required, not full
  event sourcing.
- Implement connection replacement, disconnect/grace/abandonment, Snapshot
  resync, duplicate/gap behavior and deadline continuity.
- Prove process restart recovery and safe Redis disruption behavior.
- Add deterministic concurrency, deadline, retry, reconnect, resync, restart and
  leakage suites.

**Accept:** one retry outcome/Attempt; concurrency preserves ordinal/result;
Snapshot converges after gaps; Redis cannot change durable winner; deadlines
survive restart; reliability suites pass repeatedly.

## T5 — Rematch, analytics and playtest support

**Effort:** High.

- Implement rematch request/accept/decline/expiry inside the existing Room; each
  rematch creates a new immutable Match/RuleSet/Secret.
- Add privacy-safe aggregate analytics ports/events for start, completion,
  Attempts, solve time, abandonment, reconnect, invalid/spam and rematch.
- Provide management/seed/export utilities needed for structured playtests.
- Apply accepted balance changes only through versioned presets/RuleSets.
- Fix backend playtest blockers without adding expansion features.

**Accept:** repeated Matches have no stale state/leakage; analytics contains no
raw Secret/private Guess; full guest-to-rematch API/E2E passes; preset changes
remain auditable.

## T6 — Color Classic and Permutation

**Effort:** High.

- Freeze and publish Color palette metadata, validation, feedback tagged unions,
  presets and canonical fixtures before implementation.
- Implement pure Color validators/evaluators and explicit registry entry.
- Reuse Match/Room/realtime services through the narrow game contract.
- Support Solo and Friendly snapshots/events; audit and remove proven Number-
  specific assumptions without generic over-abstraction.
- Test Classic duplicates, aggregate/positional policy, permutation validity,
  exact-count privacy, contracts and Number regressions.

**Accept:** both variants complete Solo/Friendly backend flows; Number remains
green; no duplicated lifecycle/realtime or large game-type conditional chain.

## T7 — Player-authored friendly challenges and Word spike

**Effort:** Very high, two ordered gates.

Part A:

- Freeze Challenge-per-solver and setup/commit/timeout/reveal contracts.
- Implement two protected immutable Challenges, simultaneous start, private/
  public events, reconnect during setup and Friendly-only eligibility.
- Test no-self-solve, immutability, cancel-without-result, creator visibility and
  cross-Challenge leakage.

Part B is research/prototype only:

- Prototype Persian normalization, bounded dictionary validity, candidate Word
  loop/feedback and moderation edge cases.
- Report dataset ownership/licensing, latency, false accepts/rejects and a
  go/change/no-go recommendation.
- Do not ship production Word support without a new approved task.

**Accept:** symmetric duel works safely and cannot affect rating; Word unknowns
are explicit and evidence-backed.

## T8 — Production beta hardening

**Effort:** Very high.

- Finalize security config, HTTPS/WSS, origin/host policy, throttles, admin least
  privilege, scanning, retention/deletion and audit.
- Add safe logs/traces/request IDs, metrics/dashboards/alerts, error reporting,
  feature flags and runbooks.
- Establish staging, migration/deploy/rollback compatibility, graceful ASGI
  connection behavior and backup/restore with measured RPO/RTO.
- Load/resilience test agreed concurrency, room fan-out, Guess bursts, reconnect
  storm, database contention, Redis failure and deploy/restart.
- Fix measured bottlenecks and record SLO/capacity envelope.

**Accept:** no critical security/privacy issue; restore/rollback/smoke pass;
capacity target passes with measured thresholds; operational alerts/runbooks and
feature kill switches are validated.

## T9 — Competitive planning gate, not one implementation task

After beta evidence, design Ranked fixed RuleSets, matchmaking, rating,
leaderboard/seasons, anti-farming/multi-account/disconnect abuse, report/block,
progression separation and capacity. Split the accepted plan into new bounded
vertical tasks. Do not ask one AI agent to implement all competitive features.
