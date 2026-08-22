# Think Fast Backend

Backend for **Think Fast**, a real-time deduction game for solo, head-to-head,
and multiplayer matches. Players race to discover a secret number or color
sequence under one of several rule sets.

This repository is currently in the **architecture and product-definition
phase**. The Django scaffold exists, but gameplay code has intentionally not
been implemented yet.

## Product at a glance

Think Fast has one shared match lifecycle and three initial game modes:

1. **Number Code** — guess a 5- or 6-digit secret; feedback is exact position,
   present in another position, or absent.
2. **Hidden Color Code** — guess an ordered color sequence; feedback uses
   configurable symbols such as `+`, `-`, and `0`.
3. **Color Permutation** — reorder a known (or optionally hidden) set of colors;
   feedback reveals only the number of positions that are correct.

The authoritative specification is [docs/product/game-design.md](docs/product/game-design.md).

## Planned architecture

The first release is a **modular Django monolith** with PostgreSQL, Redis,
Django REST Framework, and Django Channels. HTTP handles durable resources and
commands; WebSockets deliver live match events. Game-rule engines remain pure
Python and independent from transport and persistence.

See:

- [Architecture overview](docs/architecture/overview.md)
- [Domain model](docs/architecture/domain-model.md)
- [API and realtime contract](docs/api/realtime-contract.md)
- [Roadmap](ROADMAP.md)
- [Engineering decisions](docs/decisions/README.md)

## Repository layout

```text
apps/                 Planned bounded Django applications
config/               Django project configuration (temporary single settings file)
docs/
  api/                HTTP and WebSocket contracts
  architecture/       System and domain design
  decisions/          Architecture decision records (ADRs)
  product/            Product rules and gameplay specification
infra/                Future local/deployment infrastructure assets
scripts/              Future developer and operational scripts
tests/                Cross-application and end-to-end tests
manage.py             Django entry point
requirements.txt      Temporary dependency list until tooling is finalized
```

Each planned application has a local README defining its ownership boundary.
No empty Django packages are registered yet; application scaffolding belongs to
Roadmap Phase 1.

## Development status

- Product rules clarified: complete for planning
- Architecture and boundaries: proposed and documented
- Runtime implementation: not started
- API schema, database schema, and realtime protocol: planned, not frozen

## Quick start (current scaffold only)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py check
python manage.py runserver
```

The current settings are development-only. Do not deploy them. Environment
configuration, PostgreSQL, Redis, split settings, and secret management are
Roadmap Phase 1 deliverables.

## Working agreements

- The server is authoritative for secrets, scoring, deadlines, and match state.
- Never expose a secret in API responses, WebSocket events, logs, or analytics.
- A game mode owns evaluation rules; the match layer owns competition flow.
- Prefer deterministic, pure rule functions with exhaustive tests.
- Do not introduce microservices before measured scaling or ownership pressure.
- Record architecture-impacting changes as ADRs.

For contributor guidance, see [CONTRIBUTING.md](CONTRIBUTING.md) and
[AGENTS.md](AGENTS.md).
