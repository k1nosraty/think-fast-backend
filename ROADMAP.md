# Think Fast Backend Roadmap

The roadmap is ordered to validate the game core early and postpone expensive
multiplayer and operations work until a playable solo slice exists.

## Phase 0 — Product and architecture baseline (complete)

- Clarify the three initial modes and shared terminology.
- Define match lifecycle, fairness rules, secret ownership, and tie semantics.
- Establish modular-monolith boundaries and delivery order.
- Document API/realtime direction and initial ADRs.

**Exit:** implementation can start without deciding the system shape ad hoc.

## Phase 1 — Engineering foundation

- Pin a supported Python/Django toolchain; verify the currently declared Django
  version is available and appropriate before implementation.
- Introduce `pyproject.toml`, locked dependencies, Ruff, mypy, pytest, coverage,
  and pre-commit.
- Split settings into base/local/test/production and move all secrets to the
  environment.
- Configure PostgreSQL and Redis; add Docker Compose for local dependencies.
- Add CI for checks, tests, migrations, and dependency/security scanning.
- Scaffold `accounts`, `games`, `matches`, and `realtime` Django apps with clear
  import direction.

**Exit:** a new developer can boot the stack and CI passes on an empty domain.

## Phase 2 — Solo Number Code vertical slice (MVP foundation)

- Implement immutable rule configuration and secure secret generation.
- Implement the pure Number Code evaluator, including duplicate-policy tests.
- Model game definition, match, participant, round, attempt, and result.
- Add guest identity/session support and authenticated-user upgrade path.
- Add create/start/guess/state HTTP endpoints with idempotent guess submission.
- Add per-user rate limits and secret-redaction tests.
- Provide an OpenAPI schema and seed/demo command.

**Exit:** one player can complete a Number Code match end-to-end.

## Phase 3 — Realtime rooms and multiplayer

- Add private rooms with join codes and explicit host permissions.
- Add lobby ready/start flow, capacity limits, and reconnect snapshots.
- Publish versioned WebSocket events through Channels/Redis.
- Define authoritative server deadlines and abandonment behavior.
- Resolve simultaneous finishes with deterministic ordering and tie windows.
- Add transactional/concurrency tests for duplicate and near-simultaneous guesses.

**Exit:** 2–8 players can reliably play a server-generated shared-secret match.

## Phase 4 — Remaining rule modes

- Add Hidden Color Code with palette/length validation and symbol feedback.
- Add Color Permutation with known-palette and hidden-palette variants.
- Add player-authored secrets with commit-before-play, validation, privacy, and
  no-self-play rules.
- Add history visibility policies: full history, latest only, or none.
- Run contract tests against every mode through the shared evaluator protocol.

**Exit:** all three modes work in solo and supported multiplayer configurations.

## Phase 5 — Progression and social MVP

- Add match history, lightweight profiles, statistics, and achievements.
- Add casual matchmaking only after private rooms are stable.
- Add moderation/reporting hooks for player-authored content and display names.
- Add optional practice difficulty presets and bots/hints without affecting
  competitive scoring.

**Exit:** the product supports repeat play and safe public discovery.

## Phase 6 — Production hardening and launch

- Add structured telemetry with secret-safe logging and audit events.
- Add Sentry-compatible error reporting, health/readiness endpoints, metrics,
  dashboards, alerts, backup/restore drills, and runbooks.
- Load-test room fan-out, guess spikes, reconnect storms, and Redis failure.
- Add retention/deletion policy, privacy endpoints, abuse controls, and security
  review.
- Roll out through staging and a limited beta with feature flags.

**Exit:** SLOs, capacity envelope, recovery procedures, and launch checklist are
validated.

## Explicitly after MVP

- Ranked queues, seasons, tournaments, spectators, chat, clans
- User-generated public rule packs
- In-game economy, purchases, advertising
- Microservice extraction or multi-region active/active operation

These require product evidence and separate architecture decisions.
