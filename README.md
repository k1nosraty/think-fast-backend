# Think Fast Backend

Authoritative backend for **Think Fast**, a fast competitive deduction game.
Players solve number, color, and word challenges in solo or realtime matches.
The server owns rules, secrets, timing, accepted attempts, feedback, and results.

Backend Tasks T0–T7 are complete. MVP contracts are frozen at
`v1.0.0-draft.1`; Solo Number and private realtime Friendly 1v1 are playable.
The Room-to-rematch loop, safe playtest analytics, Color Classic and Color
Permutation and safe player-authored Friendly challenges are implemented. Word
game support is registered with a placeholder lexicon (licensed data pending).
T8 hardening and the complete single-host validation baseline are complete.
Production deployment approval remains blocked until the same operational gates
are measured on the agreed production-like staging topology. T9 competitive
planning is unblocked; this does not authorize a Production Beta release.

## MVP

The implementation baseline is deliberately narrow:

- responsive web/PWA client (maintained by the frontend team);
- guest-first identity with an account upgrade path;
- Number game as the first complete vertical slice;
- solo practice and private friendly 1v1;
- server-generated shared secrets for fair competition;
- room, ready, countdown, realtime progress, reconnect, result, and rematch;
- REST commands/snapshots plus versioned WebSocket events.

Player-authored duels and Word are explicit expansion work, not prerequisites
for the first playable MVP.
Ranked, teams, tournaments, chat, monetization, and microservices are later.

## Read this first

Humans can understand the project with this short path:

1. [Product and game rules](docs/product/game-design.md)
2. [Accepted Phase 0 decisions](docs/product/phase-0-decisions.md)
3. [Architecture and domain model](docs/architecture/overview.md)
4. [Frontend/backend contracts](docs/api/realtime-contract.md)
5. [Roadmap](ROADMAP.md)
6. [Backend AI execution tasks](docs/execution/BACKEND-TASKS.md)

Role-specific handoff:

- [Backend guide](docs/backend/README.md)
- [Quality strategy](docs/quality/README.md)
- [Production operations and T8 evidence](docs/operations/README.md)
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

## Build, validate, and run

### Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.11.33 or compatible
- Docker with Compose for local PostgreSQL 17.11 and Redis 7.4.11

### Bootstrap a clean machine

```bash
cp .env.example .env
docker compose up -d
uv sync --locked --dev
uv run python manage.py migrate
```

`manage.py` selects `config.settings.local`. Environment variables from `.env`
are not loaded implicitly; export/source them in your shell or use your process
manager. The checked-in local defaults match Compose and contain no deployable
secret. Start with `uv run python manage.py runserver`.

### Exercise the Solo API

Create a guest, then send its token as `Authorization: Bearer <token>`:

```text
POST /api/v1/guest-sessions/
GET  /api/v1/game-definitions/
POST /api/v1/solo-matches/
POST /api/v1/matches/{match_id}/guesses/
GET  /api/v1/matches/{match_id}/snapshot/
POST /api/v1/matches/{match_id}/leave/
```

Friendly lobby commands add:

```text
POST /api/v1/rooms/
POST /api/v1/rooms/{room_id}/join/
POST /api/v1/rooms/{room_id}/ready/
POST /api/v1/rooms/{room_id}/start/
POST /api/v1/rooms/{room_id}/leave/
POST /api/v1/matches/{match_id}/rematch/
WS   /ws/v1/matches/{match_id}/
WS   /ws/v1/rooms/{room_id}/
```

Native clients may send `Authorization: Bearer <token>` in the WebSocket
handshake. Browsers should request subprotocols `think-fast` and
`bearer.<token>`; query-string tokens are rejected.

Clients send `{"type":"resync","last_sequence":N}` after a detected gap.
Stored authorized events after `N` are replayed in order. Duplicates are valid
at-least-once delivery and must be ignored by sequence; an invalid cursor yields
`system.resync_required`, after which the client fetches the HTTP Snapshot.

Create a local demo identity and active match after migrations:

```bash
uv run python manage.py seed_demo
uv run python manage.py seed_playtest
```

### Run every quality gate

```bash
uv run python scripts/check.py
uv run python scripts/check_security.py
```

This runs formatting, lint, strict type checking, Django checks, migration drift,
contract validation, pytest and the 85% coverage threshold.

### Build the production image

```bash
docker build --tag think-fast-backend:t8 .
```

The image starts Daphne with `config.settings.production`. It refuses to boot
unless `DJANGO_SECRET_KEY` is strong and `DJANGO_ALLOWED_HOSTS`,
`POSTGRES_PASSWORD`, `REDIS_URL`, and `GAME_SECRET_ENCRYPTION_KEY` are explicit.
Run migrations as a separate release step before application replicas.

Run `uv run python manage.py sweep_reliability --limit 100` at least once per
second in a single scheduled worker. It converges persisted countdown/deadline
and disconnect-grace state after process restarts and retries due outbox rows.
`publish_outbox` is available when only delivery retry is desired.

Export shareable aggregate playtest data without raw guesses or secrets:

```bash
uv run python manage.py export_playtest_analytics --format json --since-days 30
```

Preview and apply privacy retention from a singleton scheduled worker:

```bash
uv run python manage.py apply_retention
uv run python manage.py apply_retention --apply --actor scheduled-retention
```

## Foundation and contract assets

```text
contracts/openapi.json                 OpenAPI 3.1 baseline
contracts/schemas/                     Versioned JSON Schemas
contracts/fixtures/                    Canonical cross-team examples
contracts/manifest.json                Validation manifest/version
scripts/validate_contracts.py          Dependency-free validator
tests/contracts/test_contracts.py      Contract and semantic example tests
config/settings/                       Explicit local/test/production settings
compose.yaml                           Local PostgreSQL and Redis
Dockerfile                             Reproducible production ASGI image
scripts/check.py                       Local/CI quality-gate entrypoint
```

## Working rule

Every implementation task must end in a demonstrable backend capability, tests,
updated contracts/docs, and a concise handoff. A task is not complete merely
because code compiles.
