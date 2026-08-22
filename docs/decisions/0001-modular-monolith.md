# ADR-0001: Modular Django monolith

- Status: Accepted
- Date: 2026-08-22

## Context

Think Fast needs several game modes, shared identities, rooms, scoring, and
realtime play. The team needs fast iteration and strong transactional behavior.

## Decision

Begin as one deployable Django system with explicit application boundaries.
Do not create microservices or one application per mode.

## Consequences

Deployment and consistency stay simple. Boundaries require review discipline.
Extraction remains possible when measurement or team ownership justifies it.
