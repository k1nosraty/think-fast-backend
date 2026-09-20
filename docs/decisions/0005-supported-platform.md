# ADR 0005 — Supported platform and dependency workflow

**Status:** Accepted in T1 on 2026-08-24

## Decision

- Runtime: CPython 3.12; project metadata permits compatible 3.13 patch releases.
- Web stack: Django 5.2.17 LTS, DRF 3.18.0, Channels 4.3.2 and
  channels-redis 4.3.0.
- Durable/ephemeral infrastructure: PostgreSQL 17.6 and Redis 7.4.5 for the
  reproducible local baseline. PostgreSQL remains authoritative; Redis remains
  disposable.
- `pyproject.toml` declares direct constraints and `uv.lock` freezes the complete
  graph. All local, CI and image builds use `uv sync --locked`/`--frozen`.
- Ruff, mypy with django-stubs, pytest/coverage and pre-commit are mandatory
  gates. Declarative settings and empty routing modules are excluded from line
  coverage; their security behavior is tested through subprocess imports.

## Rationale

Django 5.2 is the current long-term-support line and has a longer conservative
maintenance window than choosing the newest feature release. Python 3.12 is a
widely supported runtime across the selected libraries. Exact lock resolution
keeps machines, CI and containers consistent while bounded declarations make
intent visible.

## Consequences

Dependency upgrades are explicit pull requests that regenerate `uv.lock`, run
the full check command and update this ADR if a platform baseline changes.
T1 creates no gameplay model, migration, API or WebSocket consumer.
