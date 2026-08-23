# AGENTS.md — Documentation

Applies to `docs/`.

- Preserve the source-of-truth map in `docs/README.md`; do not duplicate entire
  rules or contracts across files.
- Distinguish `DECIDED`, `WORKING DEFAULT`, `EXPERIMENT`, and `LATER`. Do not turn
  a recommendation into a decision silently.
- Write for the owning audience, with concrete examples and acceptance behavior.
- Update links when moving or replacing documents and run a local-link check.
- ADRs are append-only decision history. Supersede an accepted ADR with a new
  ADR; do not rewrite its meaning.
- AI task prompts must be bounded, name exclusions, demand validation, and end
  with a handoff. They must not instruct an agent to implement future tasks.
- Keep documents concise. Prefer one canonical table to repeated prose.
