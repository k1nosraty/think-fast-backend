# AGENTS.md — Tests

Applies to cross-boundary tests under `tests/`.

- Tests assert public behavior and domain invariants, not incidental SQL count,
  private method order, or unstable representation details.
- Use deterministic clocks/random sources in tests. Never weaken production
  randomness or timing for test convenience.
- Every concurrency test must prove the invariant after both operations finish,
  not merely assert response status.
- Every realtime test must cover authorization and public/private payload
  separation where relevant.
- Add explicit secret-leakage assertions for APIs, events, snapshots, errors,
  logs, and analytics adapters touched by the task.
- Contract examples must validate against the same schema the frontend uses.
- Mark truly slow load/E2E suites explicitly; do not hide ordinary integration
  tests behind optional markers.
- Record the exact command and result in the task handoff.
