# Documentation Map

The documentation is intentionally small. Each fact has one source of truth;
other files link to it instead of copying it.

| Need | Source of truth |
| --- | --- |
| Product scope and gameplay behavior | `product/game-design.md` |
| Accepted Phase 0 values | `product/phase-0-decisions.md` |
| System boundaries and runtime behavior | `architecture/overview.md` |
| Domain concepts and invariants | `architecture/domain-model.md` |
| HTTP, WebSocket, errors, snapshot | `api/realtime-contract.md` |
| Backend implementation conventions | `backend/README.md` |
| Test and acceptance strategy | `quality/README.md` |
| Delivery order | root `ROADMAP.md` |
| Copy-ready Backend AI work units | `execution/BACKEND-TASKS.md` |
| Why an architectural choice exists | `decisions/` ADRs |

## Reading paths

Backend: architecture → domain model → contract → backend guide → assigned task.

AI: root `AGENTS.md` → relevant nested `AGENTS.md` → mandatory path above →
assigned task only.

## Documentation rule

- Product behavior changes in `game-design.md`.
- Public payload/endpoint changes in `realtime-contract.md`.
- Module/lifetime/data-flow changes in architecture docs and, when durable, an
  ADR.
- Task progress belongs in issue tracking or handoff reports, not permanent
  architecture documents.
- Do not create another document when a short section in an existing source of
  truth is enough.
