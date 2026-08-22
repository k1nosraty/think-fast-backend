# Scripts

Reserved for small, documented developer and operational entry points such as
bootstrap, checks, seed/demo data, and maintenance commands.

Prefer Django management commands for operations that need application context.
Scripts must be non-interactive in CI and safe to run repeatedly where possible.
