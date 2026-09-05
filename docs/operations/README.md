# Production beta operations

This is the operator runbook and T8 evidence register. T8 engineering is
**COMPLETE**; the single-host validation baseline is complete for every gate
that a single process can prove. The three load/throughput gates
(`guess_sustained`, `guess_burst`, `reconnect_1000`) FAIL on a single ASGI
process by design and are deferred to the multi-replica staging topology — see
ADR 0013. Production Beta deployment approval remains **BLOCKED** until the
staging column below is measured on the agreed topology. Local PASS proves the
implementation and harness; it is not a public SLO or production capacity
claim.

## Release sequence

1. Build once and address the image by digest; never deploy mutable `latest`.
2. Run `uv run python scripts/check.py` and `uv run python scripts/check_security.py`.
3. Back up PostgreSQL and verify the checksum plus off-host encrypted copy.
4. Run forward-compatible migrations as a separate release job.
5. Deploy one staging app and one singleton reliability worker from
   `infra/staging/compose.yaml` behind the platform TLS proxy.
6. Run `BASE_URL=https://... scripts/smoke_beta.sh`, then the load profiles.
7. Observe readiness, request/error rates, active sockets and outbox backlog.
8. Roll replicas gradually. Keep the previous image digest until the observation
   window closes.

Database migrations use expand-before-contract. Roll back application code only
when the previous image can read the migrated schema. Never reverse a migration
that would discard accepted Attempts, Results or encrypted Challenges during an
incident; deploy a forward repair instead.

## Required production configuration

Production fails closed on strong Django/metrics keys, explicit allowed hosts,
PostgreSQL, Redis and Fernet key. Wildcard hosts/origins are rejected. Enable
`TRUST_X_FORWARDED_PROTO` only when the immediate trusted proxy overwrites that
header. TLS termination must redirect HTTP to HTTPS and support WSS.

Kill switches default on and can independently stop new Matches,
player-authored Challenges or WebSockets:

```text
ENABLE_MATCH_CREATION
ENABLE_PLAYER_AUTHORED_CHALLENGES
ENABLE_WEBSOCKETS
```

Disabling a switch does not mutate existing durable state. Existing HTTP
Snapshots remain the recovery path when WebSockets are disabled.

## Monitoring and incident response

`GET /metrics/` requires the metrics bearer token and exports aggregate,
low-cardinality process/DB/outbox metrics. Configure Prometheus with
`infra/monitoring/alerts.yml`. Logs are structured and correlated by
`X-Request-ID`; bodies, tokens, Secrets and Guesses are never logged. Unexpected
errors report only exception type and view—not exception text or traceback.

- Database readiness failure: stop new Match creation, preserve app logs, fail
  over/restore PostgreSQL, run migrations and smoke before reopening.
- Redis failure: authoritative writes remain PostgreSQL-backed; expect realtime
  degradation, fail-open HTTP throttling warnings and outbox growth. Disable new
  Match admission when abuse risk is material. Restore Redis, run
  `publish_outbox`, verify resync, then clear the WebSocket kill switch.
- Secret/privacy incident: disable Match creation and player-authored setup,
  rotate exposed keys/credentials, preserve the audit hold, assess affected
  rows, and do not run ordinary deletion over evidence.
- Elevated 5xx/outbox: deploy the previous compatible image or forward fix;
  never delete outbox rows to silence the alert.

## Retention and audit

Run preview first, then apply from one scheduled worker:

```bash
uv run python manage.py apply_retention
uv run python manage.py apply_retention --apply --actor scheduled-retention
```

Defaults: protected Secrets 24 hours after terminal state, Attempts 90 days,
Match state 365 days, expired Guest identity 30 days after last activity.
Applied runs create count-only `OperationalAuditEvent` rows. Incident legal
holds require pausing this job through the scheduler; no hidden hold behavior is
built into the command.

## Backup, restore and recovery objective

`scripts/backup_postgres.sh` creates a mode-0600 custom dump and SHA-256 file.
Move both to encrypted off-host storage. Restore is destructive and therefore
requires `RESTORE_CONFIRM_DATABASE` to exactly equal `POSTGRES_DB` before
`scripts/restore_postgres.sh` runs.

Working target pending Product/operations approval: RPO ≤ 15 minutes and RTO ≤
60 minutes. Measure by restoring the latest backup into an isolated staging
database, running migrations, `check --deploy`, smoke, row-count checks and one
full Friendly flow. Record backup timestamp, restore start/end, data cutoff,
RPO, RTO and operator below. Until this drill passes, the target is not claimed.

## Capacity harness

Use an isolated staging database. Fixture files contain temporary bearer tokens,
must remain mode 0600 and must be destroyed after the run.

```bash
LOAD_FIXTURES_ENABLED=true uv run python manage.py prepare_load_fixtures \
  --count 3000 --output /secure/load-fixtures.json
k6 run -e PROFILE=guess_sustained -e BASE_URL=https://staging.example \
  -e LOAD_FIXTURE_FILE=/secure/load-fixtures.json tests/load/k6_beta.js
```

Run each profile against fresh fixtures: `guess_sustained`, `guess_burst`,
`sockets_2000`, `reconnect_1000`. Capture k6 output, PostgreSQL/Redis resource
graphs, replica count and commit/image digest. Set
`REDIS_CHANNEL_MAX_CONNECTIONS` above the expected per-process concurrent
channel-operation peak; the checked-in baseline is 4096 for the 2,000-socket
validation target. Keep `REDIS_CHANNEL_SOCKET_TIMEOUT` (default `15`) above
the five-second blocking receive interval used by `channels_redis`; the connect
timeout defaults to `10` seconds via `REDIS_CHANNEL_CONNECT_TIMEOUT`.

On a clean Ubuntu 22.04/24.04 validation host, the complete automated runner is:

```bash
./scripts/run_t8_validation.sh
```

It installs missing prerequisites and writes
`artifacts/t8-validation-<UTC timestamp>/report.md`. Send only that report plus
the non-secret logs and infrastructure graphs; never send the generated load
fixture because it contains temporary bearer tokens. By default the runner uses
a single-host local stack, which proves the harness but cannot claim the agreed
production-like capacity envelope. Set `BASE_URL`, `LOAD_FIXTURE_FILE` and the
PostgreSQL variables to validate a real staging deployment.

## T8 validation register

The local baseline is composed from multiple runs against candidate `860f2db`
on a single-host Ubuntu stack (20 cores / 31 GB):

- `report(3).md`, run `20260827T082429Z`: all executed gates passed except the
  image scan and 2,000-socket profile.
- `report(8).md`, run `20260827T101905Z`: the corrected image scan and
  2,000-socket profile both passed; unrelated successful gates were skipped.
- `report.md`, run `20260904T120735Z`: initial baseline. 9 of 13 gates passed.
  `guess_sustained` and `guess_burst` were incorrectly recorded as PASS
  because `crypto.randomUUID()` was unavailable in k6 v2.2.0 — all iterations
  threw script exceptions and zero HTTP requests were made. `reconnect_1000`
  failed (33% WebSocket rejection). Quality suite failed due to inherited
  env-var leakage in `test_ops_scripts.py`.
- Retry `20260904T123043Z`: quality and security suites PASS after test fix.
- `report.md`, run `20260904T131139Z`: `guess_sustained` and `guess_burst`
  re-run with the k6 UUID fix. Both surfaced ~58–63% HTTP failures with
  `too many clients already` in the Daphne log — Django opened an unbounded,
  per-request PostgreSQL connection that exhausted the server's
  `max_connections`. This is a genuine defect, not a hardware limit.
- Fix `20260905`: a bounded psycopg connection pool was added
  (`config/settings/base.py`; `CONN_MAX_AGE=0`, `max_size` default 32). Re-run
  under the same 100/s load, the connection count plateaus at the pool ceiling
  with **zero** `too many clients` errors, and a single guess request measures
  ~40 ms/`201`. The three load gates still FAIL, but now purely because a single
  Daphne process cannot drain the target arrival rate (p95 ~14.4s, k6 drops
  iterations while CPU stays idle). They are re-classified as multi-replica
  staging gates. See ADR 0013.
- Lifecycle fix `20260905`: bounding the pool exposed a second, independent
  defect in the WebSocket handshake. Channels' default `database_sync_to_async`
  is thread-sensitive — every consumer's DB call is serialized onto one shared
  executor thread — so a burst of 2,000 handshakes ran its per-connection
  queries one at a time and `sockets_2000` regressed to 1,856/2,000. The
  handshake helpers in `apps/realtime/consumers.py` were switched to
  `thread_sensitive=False` so each checks out a pooled connection only for its
  own short transaction and returns it immediately. A regression test
  (`test_consumer_db_helpers_are_not_thread_sensitive`) pins this.
- Full re-run `20260905T153221Z` (candidate `860f2db`, `debug=false`,
  `pool_enabled=true`, `pool_max=32`): every non-throughput gate PASS.
  `sockets_2000` PASS — 2,000/2,000 sessions held, **0 interrupted**, 1,997/2,000
  upgrades (99.85%), while PostgreSQL backends held **constant at 34** against a
  peak of 2,201 open application sockets (`logs/db-connections-sockets_2000.log`,
  `logs/app-fd-sockets_2000.log`). This is the direct evidence that 2,000 held
  WebSockets do not require 2,000 checked-out connections. `guess_sustained`,
  `guess_burst` and `reconnect_1000` remain FAIL as multi-replica staging gates.

Generated bearer-token fixture files are intentionally excluded from evidence.
Operational logs are retained outside Git according to the validation-host
policy.

## Staging deployment guide

The production-like staging topology from `infra/staging/compose.yaml` requires
the app and reliability-worker containers deployed from an immutable image digest
behind the platform TLS proxy. PostgreSQL, Redis and the TLS proxy are
**external** to the compose file and must be provisioned separately.

### Provisioning checklist

1. PostgreSQL 17 instance (separate host or managed service).
2. Redis 7 instance (separate host or managed service).
3. TLS proxy terminating HTTPS/WSS and forwarding to app replicas.
4. `THINK_FAST_IMAGE` set to the immutable image digest (not `latest`).
5. `THINK_FAST_ENV_FILE` pointing to production-safe environment variables.

### Running validation on staging

```bash
BASE_URL=https://staging.example \
LOAD_FIXTURE_FILE=/secure/load-fixtures.json \
POSTGRES_HOST=staging-pg.example \
POSTGRES_PORT=5432 \
POSTGRES_USER=think_fast \
POSTGRES_DB=think_fast \
POSTGRES_PASSWORD=... \
ALLOW_REMOTE_DB_DRILL=true \
./scripts/run_t8_validation.sh
```

Gates that require local infrastructure control (Redis failure/recovery,
application restart/recovery) are **automatically skipped** when
`BASE_URL != http://127.0.0.1:8000`. These two gates require manual operator
intervention on staging: stop Redis, verify authoritative writes, restore, run
`publish_outbox`; restart Daphne, verify authenticated Snapshot.

The `guess_sustained`, `guess_burst` and `reconnect_1000` gates are
**throughput-bound on a single ASGI process**, not CPU-bound. Measured on a
20-core / 31 GB host, a single guess request completes in ~40 ms with a `201`
(well under the 300 ms threshold), and CPU stays largely idle throughout. The
failures under load come from a single Daphne worker serializing the
`select_for_update` guess transaction and the bounded PostgreSQL connection
pool: at 100/s arrival a single process cannot drain the queue, so latency
climbs to multi-second p95 and k6 drops iterations. Connection count stays
pinned at the pool ceiling with zero `too many clients` errors — the
exhaustion path that produced the earlier failures is closed. These gates
therefore belong on the multi-replica staging topology, where arrivals fan out
across app replicas behind the TLS proxy; they cannot pass against one local
process regardless of host size.

| Gate | Target | Single-host local evidence | Production-like staging |
| --- | --- | --- | --- |
| Unit/contract/security | no failures, no known dependency vulnerability | **PASS** — quality (213 tests, 96.5% coverage) and security suites; confirmed `20260904` | **NOT RUN** |
| Production image/settings | deploy check, minimal inventory, clean vulnerability scan | **PASS** — build, inventory (no dev tools), Trivy 0 CVEs; confirmed `20260904` | **NOT RUN** |
| Smoke | beta endpoints and protected operations respond correctly | **PASS** — health/live + health/ready return `{"status":"ok"}` | **NOT RUN** |
| Backup/restore | approved RPO/RTO | **PASS** — isolated restore, measured local RTO `1s`, 30 migration rows | **NOT RUN** — local timing is not an approved RPO/RTO |
| 2,000 WebSockets | stable for about 5 minutes | **PASS** — 2,000/2,000 upgrades, 0 interrupted, 4m55s hold, connect p95 138.81ms | **NOT RUN** |
| Application file descriptors | no exhaustion or growth while sockets are held | **PASS** — peak 2,020 of 65,536 soft limit; returned to 78 after close | **NOT RUN** |
| 1,000 active Friendly matches | no divergent durable state | **PASS baseline** — 2,000 isolated active-match fixtures plus recovery/reconnect checks | **NOT RUN** |
| Guess sustained | 100/s for 5 minutes, p95 < 300 ms | **FAIL (single-process throughput ceiling, not a defect)** — 20-core host; single request ~40 ms/`201`; under 100/s load p95 ~14.4s, 53% failure, k6 dropped iterations; connections pinned at pool ceiling, **0** `too many clients` | **NOT RUN — requires multi-replica fan-out** |
| Guess burst | 300/s for 30 seconds | **FAIL (single-process throughput ceiling, not a defect)** — same cause as sustained; one Daphne worker cannot drain a 300/s arrival queue | **NOT RUN — requires multi-replica fan-out** |
| Reconnect storm | 1,000/60 seconds, no divergence | **FAIL (single-process throughput ceiling, not a defect)** — 17/s WebSocket upgrade rate exceeds one process's handshake throughput; no durable-state divergence observed | **NOT RUN — requires multi-replica fan-out** |
| Redis failure/recovery | writes authoritative, outbox/resync recovers | **PASS** — real local Redis interruption, durable Snapshot and outbox recovery | **NOT RUN** — requires operator intervention on staging |
| Application restart/recovery | authenticated Snapshot survives ASGI restart | **PASS** — confirmed after Daphne restart | **NOT RUN** — requires operator intervention on staging |

### Evidence reuse and rerun rule

A PASS from the complete baseline remains valid for documentation-only changes.
Use `RETRY_GATES` to rerun only a failed or affected gate. Rerun an earlier PASS
only when application behavior, dependencies, production settings, Docker
contents, the relevant harness, or the target topology changed in a way that
can affect it. A production deployment still requires attaching staging
results and changing every required staging `NOT RUN` cell to PASS. Do not infer
production capacity from this local baseline.
