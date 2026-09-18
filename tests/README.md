# Cross-Application Tests

Application-local unit tests should live beside their owning application.
This directory is reserved for integration, contract, realtime, and end-to-end
tests that intentionally cross boundaries.

Required high-risk suites include concurrent guess submission, retries and
idempotency, deadline races, reconnect snapshots, authorization isolation, and
secret-leakage regression tests.

Current T0 contract suite:

```bash
python scripts/validate_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v
```

The repository-wide baseline is `uv run python scripts/check.py`. For focused
work, run the smallest owning suite first, for example:

```bash
uv run pytest tests/contracts/
uv run pytest tests/realtime/ apps/realtime/tests/
uv run pytest tests/api/
```

Tests requiring real PostgreSQL or Redis must say so explicitly and document
their setup. A timeout, skipped dependency or unrun command is not a pass.
