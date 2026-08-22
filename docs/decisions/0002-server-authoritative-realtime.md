# ADR-0002: Server-authoritative realtime matches

- Status: Accepted
- Date: 2026-08-22

## Context

Competitive play requires consistent secrets, deadlines, attempt ordering, and
outcomes despite retries, disconnects, and untrusted clients.

## Decision

The backend owns match state and evaluates every accepted guess. HTTP commands
and database transactions establish truth; WebSockets distribute resulting
events and snapshots recover state.

## Consequences

Cheating and divergent clients are reduced. The backend must handle concurrency,
idempotency, latency, authorization, and reconnect behavior deliberately.
