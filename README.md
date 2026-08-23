# Think Fast Backend

Authoritative backend for **Think Fast**, a fast competitive deduction game.
Players solve number, color, and later word challenges in solo or realtime
matches. The server owns rules, secrets, timing, accepted attempts, feedback,
and results.

The repository is currently documentation-ready and implementation has not
started. Work must follow the roadmap and execution prompts rather than adding
features ad hoc.

## MVP

The implementation baseline is deliberately narrow:

- responsive web/PWA client (maintained by the frontend team);
- guest-first identity with an account upgrade path;
- Number game as the first complete vertical slice;
- solo practice and private friendly 1v1;
- server-generated shared secrets for fair competition;
- room, ready, countdown, realtime progress, reconnect, result, and rematch;
- REST commands/snapshots plus versioned WebSocket events.

Color variants follow after the 1v1 core is reliable. Player-authored duels and
Word are explicit expansion work, not prerequisites for the first playable MVP.
Ranked, teams, tournaments, chat, monetization, and microservices are later.

## Read this first

Humans can understand the project with this short path:

1. [Product and game rules](docs/product/game-design.md)
2. [Architecture and domain model](docs/architecture/overview.md)
3. [Frontend/backend contracts](docs/api/realtime-contract.md)
4. [Roadmap](ROADMAP.md)
5. [Backend AI execution tasks](docs/execution/BACKEND-TASKS.md)

Role-specific handoff:

- [Backend guide](docs/backend/README.md)
- [Quality strategy](docs/quality/README.md)
- [Documentation map and source-of-truth rules](docs/README.md)

AI agents must read [AGENTS.md](AGENTS.md) before acting. More-specific
`AGENTS.md` files apply under `apps/`, `docs/`, and `tests/`.

## Planned structure

```text
apps/                 Django bounded applications (created in Task T1)
config/               Django project and environment settings
docs/                  Product, architecture, contracts, handoff, and execution
infra/                 Local/deployment infrastructure
scripts/               Repeatable developer and operational helpers
tests/                 Cross-boundary contract, integration, and E2E tests
```

## Architecture in one paragraph

Start as a modular Django monolith. Pure game evaluators validate and score a
secret/guess without importing Django. Application services authorize commands,
manage transactions and lifecycle, call evaluators, persist results, and emit
events. PostgreSQL is the source of truth; Redis supports realtime delivery and
ephemeral coordination. WebSocket delivery never decides match state.

## Current scaffold

The existing Django settings are development-only and contain scaffold values.
Task T1 replaces them with environment-based settings, PostgreSQL/Redis,
tooling, CI, and a reproducible local stack. Until T1 is complete, do not deploy
the project.

## Working rule

Every implementation task must end in a demonstrable backend capability, tests,
updated contracts/docs, and a concise handoff. A task is not complete merely
because code compiles.
