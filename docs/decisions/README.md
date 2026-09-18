# Architecture Decision Records

ADRs capture decisions that materially constrain implementation.

- [ADR-0001: Modular Django monolith](0001-modular-monolith.md)
- [ADR-0002: Server-authoritative realtime matches](0002-server-authoritative-realtime.md)
- [ADR-0003: Pure mode evaluators](0003-pure-mode-evaluators.md)
- [ADR-0004: PostgreSQL truth and Redis delivery](0004-postgres-redis.md)
- [ADR-0005: Supported platform and dependency policy](0005-supported-platform.md)
- [ADR-0006: Solo secret and guest identity](0006-solo-secret-and-identity.md)
- [ADR-0007: Friendly room and realtime lifecycle](0007-friendly-room-realtime.md)
- [ADR-0008: Rematch and playtest analytics](0008-rematch-and-playtest-analytics.md)
- [ADR-0009: Color contract and evaluator registry](0009-color-contract-and-registry.md)
- [ADR-0010: Player-authored challenges](0010-player-authored-challenges.md)
- [ADR-0011: Production beta controls and evidence gate](0011-production-beta-controls.md)
- [ADR-0012: T8 evidence composition and T9 planning boundary](0012-t8-evidence-and-t9-planning.md)
- [ADR-0013: T8 connection pool fix and load-gate topology](0013-t8-connection-pool-and-load-gate-topology.md)
- [ADR-0014: Party Mode Core Gameplay Redesign](0014-party-mode-gameplay-redesign.md)

ADR-0014 supersedes ADR-0007's two-member assumption only for Party Mode:
Friendly remains a two-player mode, while Party supports 2–8 participants.
Implementation and live E2E evidence are tracked in T10 and the workspace
[`TASKS.md`](../../../TASKS.md).

Use the next sequential number. State context, decision, consequences, and
status. Supersede old decisions; do not silently rewrite their history.

Before adding an ADR, confirm the choice is durable and materially constrains
future work. Routine implementation notes, task status and local setup belong
in their owning README, task or handoff instead. Link a superseding ADR from
the older record while preserving the older record's accepted history.
