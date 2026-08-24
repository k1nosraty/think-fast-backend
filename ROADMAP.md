# Think Fast Delivery Roadmap

The roadmap uses a small number of substantial vertical tasks. Each task has a
copy-ready AI prompt and acceptance criteria in
[`docs/execution/BACKEND-TASKS.md`](docs/execution/BACKEND-TASKS.md). This is the
Backend roadmap; the React team receives a separate handoff package and task
plan. Cross-team implementation starts only after the shared contract is frozen.

| Task | Milestone | Playable outcome |
| --- | --- | --- |
| T0 | Decision and contract freeze | **Complete** — MVP rules and v1 draft contract frozen |
| T1 | Engineering foundation | **Complete** — reproducible local/CI backend foundation |
| T2 | Solo Number vertical slice | **Complete** — guest completes a Number match end-to-end |
| T3 | Private room and realtime 1v1 | **Complete** — two guests play a shared-secret match |
| T4 | Reliability and recovery | **Complete** — retry, deadlines, resync, restart, and reconnect are safe |
| T5 | Rematch and gameplay polish | **Complete** — play-rematch loop and safe playtest analytics |
| T6 | Color expansion | Color Classic and Permutation use the shared match platform |
| T7 | Challenge expansion | Player-authored duel plus a bounded Word feasibility spike |
| T8 | Production beta | Secure, observable, load-tested staged release |
| T9 | Competitive product | Ranked/matchmaking/progression only after MVP evidence |

## Release boundaries

### Foundation release — T0–T1

The team can develop against stable conventions, contracts, local dependencies,
and CI. No gameplay promise is made yet.

### First playable — T2

Number Solo proves rules, persistence, API, guest identity, feedback, result,
and secret safety through one vertical slice.

### Social MVP — T3–T5

Private friendly 1v1 is realtime, recoverable, and replayable. This is the first
candidate for closed user playtesting.

### Game expansion — T6–T7

Color confirms that shared match architecture is genuinely reusable.
Player-authored challenges arrive after fair system-secret competition. Word is
implemented only if its validation/feedback spike passes explicit gates.

### Beta — T8

Operations, security, retention, monitoring, backup/restore, and capacity are
validated before external release.

### Post-MVP — T9

Ranked, rating, leaderboard, public matchmaking, achievements, party/team,
spectators, tournaments, chat, cosmetics, and monetization require product data
and separate execution plans.

## Phase exit rule

A task closes only when:

- its acceptance criteria pass;
- frontend/backend contracts and canonical examples are current;
- required tests pass in CI;
- migrations and operational impact are documented;
- the vertical outcome is demonstrated on the supported client path;
- unresolved limitations are recorded rather than hidden.
