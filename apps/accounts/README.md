# Accounts boundary

Owns the minimal 30-day sliding Guest identity, hashed bearer tokens,
authentication and public identity serialization. It deliberately does not own
registration, passwords, OTP, gameplay state or Room membership. Account
upgrade remains future scope until a task defines its security and migration
contract.

Run its focused suite with `uv run pytest apps/accounts/tests/`.
