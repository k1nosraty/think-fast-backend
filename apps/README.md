# Application Boundaries

Planned Django applications:

| Application | Owns | Must not own |
| --- | --- | --- |
| `accounts` | guest/user identity, profile, account lifecycle | game rules, room state |
| `games` | mode definitions, rule configs, pure evaluators, secret generation | matchmaking, WebSockets |
| `matches` | rooms, participants, rounds, attempts, scoring, lifecycle | evaluator internals, transport |
| `realtime` | WebSocket consumers, event serialization, reconnect delivery | authoritative game decisions |
| `progression` | history projections, statistics, achievements (post-MVP) | core match writes |

Each application should contain a local README when scaffolded. Cross-app work
is coordinated through explicit application services and stable domain values,
not direct access to another app's internal models.

Dependency direction:

```text
transport (HTTP/WebSocket) -> application services -> domain rules
                                      |
                                      v
                               persistence/adapters
```

The `games` rule layer must be importable and testable without Django setup.
