# ADR 0011 — Production beta controls and evidence gate

**Status:** Accepted implementation baseline in T8 on 2026-08-26; staging exit pending

## Decision

- Production configuration fails closed; wildcard hosts/origins and short
  operational tokens are rejected. Proxy TLS headers are trusted only by an
  explicit environment switch.
- Feature kill switches stop admission, never rewrite authoritative state.
- Metrics are aggregate, low-cardinality and bearer-protected. Logs contain
  request correlation but no request bodies or exception text.
- Admin models are inspection-only. Mutating maintenance runs through explicit,
  audited commands.
- Retention destroys protected material on schedule and records count-only audit
  evidence. Backups are checksummed, permission-restricted and restored only
  with exact target confirmation.
- Capacity is approved only from the repeatable staging harness. Missing Docker,
  PostgreSQL, Redis or staging evidence is a blocker, never an assumed pass.
- Redis-backed throttling fails open during a verified cache outage so durable
  PostgreSQL commands and Snapshots remain available. This emits a degraded-
  security warning; operators must disable new Match admission if abuse risk is
  elevated. Readiness still fails until Redis recovers.
- The Channels Redis pool is explicitly capacity-sized through
  `REDIS_CHANNEL_MAX_CONNECTIONS` (default 4096) instead of inheriting the
  redis-py default of 100 connections.
- T8 refreshes patch baselines to Python 3.12.14, PostgreSQL 17.11 and Redis
  7.4.11; this supersedes only the older patch numbers in ADR 0005, not its
  platform/dependency policy.

## Consequences

T8 may produce a hardened release candidate without declaring Production Beta
complete. Operations must attach backup/restore, load, dependency-failure and
deploy/restart measurements before the roadmap exit is marked complete.
