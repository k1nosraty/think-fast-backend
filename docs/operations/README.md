# Production beta operations

This is the operator runbook and T8 evidence register. T8 code hardening is
implemented, but the Production Beta exit remains **BLOCKED** until the staging
rows marked `NOT RUN` are measured on the agreed topology.

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
  degradation and outbox growth. Restore Redis, run `publish_outbox`, verify
  resync, then clear the WebSocket kill switch.
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
graphs, replica count and commit/image digest.

## T8 validation register

| Gate | Target | Current evidence |
| --- | --- | --- |
| Unit/contract/security | no failures, no known dependency vulnerability | Local automated gates available |
| Production settings | Django deploy check clean | Local automated gate available |
| Backup/restore | approved RPO/RTO | **NOT RUN — PostgreSQL/staging unavailable** |
| 2,000 WebSockets | stable for 5 minutes | **NOT RUN** |
| 1,000 active Friendly matches | no divergent durable state | **NOT RUN** |
| Guess sustained | 100/s for 5 minutes, p95 < 300 ms | **NOT RUN** |
| Guess burst | 300/s for 30 seconds | **NOT RUN** |
| Reconnect storm | 1,000/60 seconds, no divergence | **NOT RUN** |
| Redis failure/recovery | writes authoritative, outbox/resync recovers | Hermetic behavior tested; real Redis drill **NOT RUN** |
| Deploy/restart | graceful reconnect and compatible rollback | Harness/runbook ready; staging drill **NOT RUN** |

Production Beta approval requires attaching measured results and changing every
required `NOT RUN` row to PASS. Do not infer capacity from unit-test speed.
