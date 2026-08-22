# ADR-0004: PostgreSQL truth and Redis delivery

- Status: Accepted
- Date: 2026-08-22

## Context

Matches need durable, transactional state and low-latency fan-out/presence.
Treating ephemeral realtime infrastructure as truth risks data loss and split
outcomes.

## Decision

PostgreSQL is the authoritative store. Redis supports Channels delivery,
presence, rate limiting, and caches. Redis state may accelerate behavior but
must be reconstructible or safely disposable.

## Consequences

Critical outcomes survive Redis loss. Realtime delivery needs snapshots,
sequence numbers, and possibly a transactional outbox for reliable fan-out.
