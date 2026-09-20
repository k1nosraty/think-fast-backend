# ADR 0006 — Solo identity, protected Secret and lifecycle

**Status:** Accepted in T2 on 2026-08-24

## Decision

- A guest receives one opaque bearer token. Only its SHA-256 digest is stored;
  activity extends expiry to 30 days at most once per day.
- Challenge Secret is encrypted separately using a production-required Fernet
  key. It is absent from ordinary Match/Participant/Attempt models, admin lists,
  logs and active snapshots.
- Creating a Solo Match activates it immediately, as frozen by the T0 HTTP
  contract. Start time and deadline are server timestamps.
- Match and Participant rows are locked for Guess writes. Database constraints
  enforce unique command and ordinal identities. Invalid Guess creates nothing;
  a retry returns its existing Attempt; a new command for the same Guess creates
  a new Attempt.
- Deadline and attempt-limit exhaustion produce `unsolved`; solving produces
  `won`; leaving produces `abandoned`. Normal terminal results reveal the Secret
  while abandonment does not.

## Consequences

Key rotation and the 24-hour terminal Secret deletion job remain production
operations work; losing the encryption key makes active challenges unreadable.
T2 contains no Room, Friendly participant, WebSocket event or rematch behavior.
