# Architecture Overview

## Approach

Build a modular Django monolith. The product is early, the domain boundaries are
clear enough for internal modules, and multiplayer consistency benefits from a
single transactional authority. Separate services would add distributed state
and operational cost before providing useful isolation.

## Runtime components

- **Django + DRF:** authentication, durable resources, commands, admin, OpenAPI
- **Django Channels:** room subscriptions and live events
- **PostgreSQL:** source of truth for users, rules, matches, attempts, results
- **Redis:** Channels layer, short-lived presence, rate-limit/cache coordination
- **Worker queue (when justified):** notifications, analytics projection, and
  cleanup; never authoritative guess evaluation

## Layering

1. **Transport:** serializers, API views, consumers, protocol validation.
2. **Application:** use cases such as start match and submit guess; transactions,
   authorization, orchestration, and event creation.
3. **Domain:** immutable rule values, state-transition rules, evaluators, scoring.
4. **Infrastructure:** ORM repositories, Redis delivery, clocks, random source.

Domain evaluation must not import Django, access the database, publish events,
or read wall-clock time.

## Core interaction: submit guess

1. Authenticate participant and validate command/idempotency key.
2. Lock or atomically advance the participant round state.
3. Confirm match is active and server deadline has not passed.
4. Normalize the guess under the frozen rule configuration.
5. Load the protected secret and call the mode evaluator.
6. Persist attempt, feedback, sequence number, and any terminal result in one
   transaction.
7. Commit an outbox event.
8. Deliver authorized events after commit; clients can recover via snapshot.

The database commit decides the outcome. WebSocket delivery never decides game
state.

## Consistency and concurrency

- Unique `(participant_round, attempt_number)` and idempotency constraints stop
  duplicated attempts.
- Use row locking or an equivalent compare-and-set strategy for concurrent
  guesses and completion.
- Assign monotonic match event sequence numbers for ordering and gap detection.
- Persist events in an outbox when reliable post-commit fan-out is required.
- A reconnecting client requests a snapshot plus the latest sequence number.

## Security and privacy

- Secrets are sensitive gameplay data, even if not personal data.
- Store secret material separately from ordinary client-facing projections and
  restrict access through one application service.
- Redact secrets and player-authored codes from logs, tracing, error payloads,
  admin list views, and analytics.
- Use environment-based secrets, secure cookies/tokens, HTTPS/WSS, origin checks,
  per-user/IP throttles, and strict room authorization.
- Reveal secrets only according to a documented post-round policy.

## Scaling path

Scale stateless ASGI instances horizontally, backed by PostgreSQL and Redis.
Partition Channels groups by match. Measure database contention, event fan-out,
and Redis memory before extracting anything. Potential future extraction points
are matchmaking and analytics—not the rule evaluator by default.

## Non-goals for the first architecture

- Microservices, event sourcing, Kafka, Kubernetes, or a generic plugin platform
- Client-authoritative outcomes
- Persisting transient presence as core match truth
- One Django app per game mode
