# Scripts

`check.py` is the single non-interactive quality entrypoint used locally and in
CI. `validate_contracts.py` remains the dependency-free T0 contract validator.

Prefer Django management commands for operations that need application context.
Scripts must be non-interactive in CI and safe to run repeatedly where possible.
