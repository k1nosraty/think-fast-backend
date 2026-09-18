# Infrastructure

Reserved for reviewed local and deployment infrastructure assets.

T1 provides `compose.yaml` for pinned PostgreSQL/Redis dependencies,
`.env.example`, operational probes and a non-root ASGI `Dockerfile`. Start local
dependencies with `docker compose up -d`; do not commit `.env`.

T8 adds an environment-driven staging app/worker composition and Prometheus
alert rules. TLS, PostgreSQL, Redis, secret storage and encrypted backup storage
remain platform-managed; no credentials belong in this directory. See
`docs/operations/README.md` for deploy, incident and capacity procedures.

For a local host where `5432` is already occupied, override only the published
PostgreSQL port and pass the same value to Django:

```bash
POSTGRES_PORT=5433 docker compose up -d
POSTGRES_PORT=5433 uv run python manage.py migrate
```

Compose reads `.env`; Django does not. Export custom values into the process
environment whenever they must be shared by both.
