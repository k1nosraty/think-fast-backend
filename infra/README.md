# Infrastructure

Reserved for reviewed local and deployment infrastructure assets.

T1 provides `compose.yaml` for pinned PostgreSQL/Redis dependencies,
`.env.example`, operational probes and a non-root ASGI `Dockerfile`. Start local
dependencies with `docker compose up -d`; do not commit `.env`.

Provider-specific production configuration remains future work and must live in
explicit subdirectories without secrets.
