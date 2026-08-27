# Scripts

`check.py` is the single non-interactive quality entrypoint used locally and in
CI. `validate_contracts.py` remains the dependency-free T0 contract validator.

Prefer Django management commands for operations that need application context.
Scripts must be non-interactive in CI and safe to run repeatedly where possible.

T8 adds `check_security.py`, staging smoke, checksummed PostgreSQL backup/restore
and a Word-spike benchmark. Restore requires an exact database confirmation and
is never part of an ordinary automated check.

`run_t8_validation.sh` is the Ubuntu one-command validation runner. It installs
Docker, PostgreSQL client tools, k6, Trivy and pinned uv when needed; starts a
uniquely named local dependency stack by default; runs quality/security, builds
and scans the production image, performs smoke and isolated restore drills,
runs every capacity profile, interrupts/restarts Redis and restarts ASGI; then
writes a private Markdown report under `artifacts/`. A local single-host run
validates the harness but is not a substitute for the agreed production-like
staging topology.

```bash
./scripts/run_t8_validation.sh
```

For a deployed staging API, generate fixtures on that isolated environment and
run with explicit inputs:

```bash
BASE_URL=https://api.staging.example.com \
LOAD_FIXTURE_FILE=/secure/load-fixtures.json \
POSTGRES_HOST=... POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=... \
ALLOW_REMOTE_DB_DRILL=true \
./scripts/run_t8_validation.sh
```

Set `INSTALL_PREREQUISITES=false` when the host is pre-provisioned,
`RUN_LOAD_TESTS=false` for a short diagnostic run, or `KEEP_STACK=true` to keep
the local PostgreSQL/Redis containers after completion. A remote database drill
is skipped unless `ALLOW_REMOTE_DB_DRILL=true`, because it creates and later
drops a uniquely named temporary database on the supplied server. Reports intentionally
exclude credentials and load-fixture contents; never send the fixture file.
