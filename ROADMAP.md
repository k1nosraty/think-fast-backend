# Think Fast Delivery Roadmap

The roadmap uses a small number of substantial vertical tasks. Each task has a
copy-ready AI prompt and acceptance criteria in
[`docs/execution/BACKEND-TASKS.md`](docs/execution/BACKEND-TASKS.md). This is the
Backend roadmap; the React team receives a separate handoff package and task
plan. Cross-team implementation starts only after the shared contract is frozen.

| Task | Milestone | Playable outcome |
| --- | --- | --- |
| T0–T7 | Foundation through Challenge | **Implemented · Unit-tested** — see the bounded task records and their evidence |
| T8 | Production beta | **Implemented · Unit-tested** — single-host baseline passes; staging and production approval remain pending |
| T9 | Competitive product | **Ready for planning** — split Ranked/matchmaking/progression into bounded tasks before implementation |
| T10 | Party Mode Core Gameplay Redesign | **Implemented · Unit-tested · E2E-verified** — 1 Creator → Multiple Guessers (2–8), 60s timer, placement scoring, rotation and rematch |

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
validated before external release. The single-host engineering baseline is
complete; external release still requires evidence from the agreed
production-like staging topology.

### Post-MVP — T9

Ranked, rating, leaderboard, public matchmaking, achievements, party/team,
spectators, tournaments, chat, cosmetics, and monetization require product data
and separate execution plans. T9 planning may proceed from the accepted T8
engineering baseline, but it does not waive the staging gate for Production
Beta deployment.

## Phase exit rule

A task closes only when:

- its acceptance criteria pass;
- frontend/backend contracts and canonical examples are current;
- required tests pass in CI;
- migrations and operational impact are documented;
- the vertical outcome is demonstrated on the supported client path;
- unresolved limitations are recorded rather than hidden.

The cross-repository status source is the workspace [`TASKS.md`](../TASKS.md).
After TF-05, the next task is TF-06 (cross-repository CI); no Backend roadmap
entry is `Staging-verified` or `Production-approved` yet.
