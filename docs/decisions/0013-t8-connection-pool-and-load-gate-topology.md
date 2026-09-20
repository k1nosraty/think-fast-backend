# ADR 0013 — T8 connection pool fix and load-gate topology

**Status:** Accepted on 2026-09-05. Supersedes the load-evidence claims of
ADR 0012.

## Context

ADR 0012 recorded the T8 Guess-load gates as PASS. That record was wrong. The
PASS came from a k6 defect: `crypto.randomUUID()` was unavailable in k6 v2.2.0,
so every load iteration threw a script exception and **zero** HTTP requests
reached the application. When the harness was corrected (run `20260904T131139Z`)
the gates failed with 58–63% HTTP errors, and the Daphne log showed 14,152
occurrences of PostgreSQL `FATAL: sorry, too many clients already`.

Investigation on the actual validation host (20 cores / 31 GB — not the
"2-core" machine the earlier register claimed) established the real cause.
Django's ASGI handler runs each in-flight request on its own thread-sensitive
executor thread. With persistent connections (`CONN_MAX_AGE > 0`) each thread
pins its own PostgreSQL connection, so connection count tracks request
concurrency with no upper bound. Under the 100/s and 300/s Guess profiles this
exceeded the server's `max_connections` and requests failed at connect time.
The failure was a connection-management defect, not CPU saturation.

## Decision

- Put the `default` database behind a bounded psycopg connection pool
  (`config/settings/base.py`): `POSTGRES_POOL_ENABLED` (default true),
  `min_size` 4, `max_size` 32, `timeout` 10s, with `CONN_MAX_AGE=0` and
  `CONN_HEALTH_CHECKS=True`. Pooling and Django persistent connections are
  mutually exclusive, so `CONN_MAX_AGE` is forced to 0 whenever the pool is on.
  `max_size` 32 is deliberately conservative so that several app replicas
  (32 × replicas) stay within a standard 100-connection PostgreSQL limit.
- The T8 validation runner exports `DJANGO_DEBUG=false` and
  `POSTGRES_POOL_ENABLED=true` explicitly, so capacity measurement never runs
  with query logging on and never silently disables the pool.
- Classify `guess_sustained`, `guess_burst` and `reconnect_1000` as
  **multi-replica staging gates**, not single-host local gates. A single Daphne
  process serializes the `select_for_update` guess transaction behind the pool;
  at the target arrival rate one process cannot drain the queue regardless of
  host size. They are expected to FAIL locally and must be measured on the
  staging topology where arrivals fan out across app replicas.

## Evidence

Measured on the 20-core / 31 GB host, candidate `860f2db` plus the pool change:

- Single guess request: **~40 ms**, HTTP `201` — far under the 300 ms threshold.
- Under 100/s load with the pool enabled: connection count plateaus at the pool
  ceiling (34 at `max_size` 32; 82 at `max_size` 80), with **zero**
  `too many clients` errors across three separate runs. The exhaustion path is
  closed.
- The gates still FAIL under load (p95 ~14.4s, ~53% k6 check failures, dropped
  iterations) while CPU stays largely idle — a single-process throughput
  ceiling, confirmed by the ~40 ms isolated service time.

## Consequences

The connection-exhaustion defect that ADR 0012 masked is fixed and proven. The
load gates now carry an honest status: FAIL locally for a understood,
non-defect reason, deferred to staging. ADR 0012's evidence-composition and
T9-planning-boundary decisions are otherwise unchanged; only its claim that the
load gates passed is superseded here. Production deployment and capacity
approval remain gated by ADR 0011 and the staging register in
`docs/operations/README.md`.
