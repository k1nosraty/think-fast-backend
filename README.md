# Think Fast Backend

Authoritative backend for **Think Fast**, a fast competitive deduction game.
Players solve number, color, and later word challenges in solo or realtime
matches. The server owns rules, secrets, timing, accepted attempts, feedback,
and results.

Backend Task T0 is complete: MVP decisions, OpenAPI, JSON Schemas, canonical
fixtures, and dependency-free contract tests are frozen at
`v1.0.0-draft.1`. Gameplay implementation has not started. The next task is T1;
do not skip directly to T2.

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
2. [Accepted Phase 0 decisions](docs/product/phase-0-decisions.md)
3. [Architecture and domain model](docs/architecture/overview.md)
4. [Frontend/backend contracts](docs/api/realtime-contract.md)
5. [Roadmap](ROADMAP.md)
6. [Backend AI execution tasks](docs/execution/BACKEND-TASKS.md)

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

## Build, validate, and run the current scaffold

### Requirements

- Python with `venv` and `pip`
- No PostgreSQL or Redis is required in T0

The repository currently retains the original scaffold dependency file. T1
must verify/pin the supported Python/Django toolchain and replace this temporary
workflow; do not treat it as the final production build.

### Create the local environment

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Validate T0 contracts and tests

These checks use only Python's standard library and can run before installing
Django:

```bash
python scripts/validate_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v
```

Expected T0 result:

```text
Contract validation passed: 1 OpenAPI document, 7 canonical fixtures
Ran 6 tests
OK
```

### Check and run the Django scaffold

After installing `requirements.txt`:

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

This starts only the original Django scaffold; no gameplay endpoint exists yet.

### Production build status

There is intentionally no supported production image/build in T0. Task T1 owns
the pinned dependency lock, split settings, PostgreSQL/Redis local stack, CI,
container/build procedure, production checks, and reproducible deployment
artifact. Deploying the current development settings is unsupported.

## Current scaffold and contract assets

The existing Django settings are development-only and contain scaffold values.
Task T1 replaces them with environment-based settings, PostgreSQL/Redis,
tooling, CI, and a reproducible local stack. Until T1 is complete, do not deploy
the project.

```text
contracts/openapi.json                 OpenAPI 3.1 baseline
contracts/schemas/                     Versioned JSON Schemas
contracts/fixtures/                    Canonical cross-team examples
contracts/manifest.json                Validation manifest/version
scripts/validate_contracts.py          Dependency-free validator
tests/contracts/test_contracts.py      Contract and semantic example tests
```

## Working rule

Every implementation task must end in a demonstrable backend capability, tests,
updated contracts/docs, and a concise handoff. A task is not complete merely
because code compiles.
