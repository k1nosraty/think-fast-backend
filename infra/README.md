# Infrastructure

Reserved for reviewed local and deployment infrastructure assets.

T1 provides `compose.yaml` for pinned PostgreSQL/Redis dependencies,
`.env.example`, operational probes and a non-root ASGI `Dockerfile`. Start local
dependencies with `docker compose up -d`; do not commit `.env`.

T8 adds an environment-driven staging app/worker composition and Prometheus
alert rules. TLS, PostgreSQL, Redis, secret storage and encrypted backup storage
remain platform-managed; no credentials belong in this directory. See
`docs/operations/README.md` for deploy, incident and capacity procedures.
