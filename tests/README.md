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
