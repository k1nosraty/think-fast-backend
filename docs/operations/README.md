# Production beta operations

This is the operator runbook and T8 evidence register. T8 engineering and its
single-host validation baseline are **COMPLETE**. Production Beta deployment
approval remains **BLOCKED** until the staging column below is measured on the
agreed topology. Local PASS proves the implementation and harness; it is not a
public SLO or production capacity claim.

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

The local baseline is composed from one complete run and one selective retry
against the same candidate (`c890c69`) on a two-core Ubuntu host:

- `report(3).md`, run `20260827T082429Z`: all executed gates passed except the
  image scan and 2,000-socket profile.
- `report(8).md`, run `20260827T101905Z`: the corrected image scan and
  2,000-socket profile both passed; unrelated successful gates were skipped.

Generated bearer-token fixture files are intentionally excluded from evidence.
Operational logs are retained outside Git according to the validation-host
policy.

| Gate | Target | Single-host local evidence | Production-like staging |
| --- | --- | --- | --- |
| Unit/contract/security | no failures, no known dependency vulnerability | **PASS** — quality and security suites | **NOT RUN** |
| Production image/settings | deploy check, minimal inventory, clean vulnerability scan | **PASS** — build, inventory and Trivy scan | **NOT RUN** |
| Smoke | beta endpoints and protected operations respond correctly | **PASS** | **NOT RUN** |
| Backup/restore | approved RPO/RTO | **PASS** — isolated restore, measured local RTO `0s`, 30 migration rows | **NOT RUN** — local timing is not an approved RPO/RTO |
| 2,000 WebSockets | stable for about 5 minutes | **PASS** — 2,000/2,000 upgrades, 0 interrupted, 4m55s hold, connect p95 574.31ms | **NOT RUN** |
| Application file descriptors | no exhaustion or growth while sockets are held | **PASS** — peak/steady 2,021 of 65,536 soft limit; returned after close | **NOT RUN** |
| 1,000 active Friendly matches | no divergent durable state | **PASS baseline** — 2,000 isolated active-match fixtures plus recovery/reconnect checks | **NOT RUN** |
| Guess sustained | 100/s for 5 minutes, p95 < 300 ms | **PASS** — k6 thresholds satisfied | **NOT RUN** |
| Guess burst | 300/s for 30 seconds | **PASS** — k6 thresholds satisfied | **NOT RUN** |
| Reconnect storm | 1,000/60 seconds, no divergence | **PASS** — k6 and authenticated recovery checks | **NOT RUN** |
| Redis failure/recovery | writes authoritative, outbox/resync recovers | **PASS** — real local Redis interruption, durable Snapshot and outbox recovery | **NOT RUN** |
| Application restart/recovery | authenticated Snapshot survives ASGI restart | **PASS** | **NOT RUN** |

### Evidence reuse and rerun rule

A PASS from the complete baseline remains valid for documentation-only changes.
Use `RETRY_GATES` to rerun only a failed or affected gate. Rerun an earlier PASS
only when application behavior, dependencies, production settings, Docker
contents, the relevant harness, or the target topology changed in a way that
can affect it. A production deployment still requires attaching staging
results and changing every required staging `NOT RUN` cell to PASS. Do not infer
production capacity from this local baseline.
