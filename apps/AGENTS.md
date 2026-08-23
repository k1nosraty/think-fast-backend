# AGENTS.md — Backend Applications

Applies to future code under `apps/`.

## Boundaries

- `accounts`: guest/user identity and account lifecycle.
- `games`: rules, secret generation contracts, pure evaluators, and game
  definitions; no room/realtime ownership.
- `matches`: room/match/challenge/attempt/result lifecycle and application
  services; no evaluator internals or WebSocket consumers.
- `realtime`: transport authentication, subscriptions, serialization, and
  delivery; no authoritative outcome decisions.
- later modules such as competition/progression consume final results/events and
  never modify the core match transaction.

## Dependency direction

```text
HTTP/WebSocket adapters -> application services -> pure domain/evaluators
                                  |
                                  v
                        ORM/cache/event adapters
```

- Never import transport code into domain or application services.
- Do not access another application's private ORM details from views/consumers.
  Use an explicit service or stable public value.
- Evaluators return semantic values (`exact`, `present`, `absent`,
  `exact_count`), never colors, glyphs, translated text, or HTTP responses.
- Do not expose a general secret serializer. Secret access is an explicit,
  audited application concern.
- All accepted guess writes, ordinal allocation, feedback persistence, terminal
  transitions, and outbox/event creation occur atomically.

## Testing

Keep pure unit tests close to the owning application. Put cross-application,
protocol, concurrency, and E2E tests under root `tests/` and follow its
`AGENTS.md`.
