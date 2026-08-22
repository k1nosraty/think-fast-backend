# Agent Instructions

Read `README.md`, `ROADMAP.md`, `docs/product/game-design.md`, and
`docs/architecture/overview.md` before changing the project.

## Current phase

The repository is prepared for implementation but contains no gameplay code.
Do not silently invent unresolved product rules. Use the defaults documented in
the product specification and surface decisions that change fairness, privacy,
scoring, or compatibility.

## Architecture constraints

- Start as a modular Django monolith.
- Keep rule evaluation in pure Python, independent of Django ORM and transport.
- Keep match lifecycle separate from mode-specific evaluation.
- Treat the backend as authoritative; clients render state and submit commands.
- Use stable UUIDs externally. Never make database row order part of a contract.
- Do not store raw secrets in logs, analytics events, exception context, or
  client-visible payloads.
- REST endpoints and WebSocket events must be versioned and documented.
- Match mutations must be transactional and idempotent where retries are valid.
- Avoid a generic plugin framework for three known modes. A small explicit mode
  registry and a narrow evaluator protocol are sufficient.

## Quality bar

- Tests accompany every rule and state transition.
- Include boundary, invalid-input, concurrency, reconnect, timeout, and secret-
  leakage cases.
- Add migrations with model changes; never rewrite an applied migration.
- Update relevant docs and ADRs in the same change.
- Run formatting, linting, type checks, Django checks, and tests before handoff.

## Scope discipline

Follow `ROADMAP.md`. Phase 1 establishes foundations; Phase 2 delivers a solo
vertical slice before multiplayer complexity. Do not add tournaments, chat,
ranked matchmaking, or monetization to the MVP unless the roadmap is revised.
