# Think Fast Product and Game Rules

This is the product-behavior source of truth shared by Product, Frontend,
Backend, QA, and AI agents. Technical schemas live in the contract document.

## Product definition

Think Fast is a realtime competitive deduction platform: players solve a
system- or player-created challenge using limited feedback, under time and/or
attempt pressure.

Every feature should strengthen at least one pillar:

- **Fast:** short setup and short matches.
- **Smart:** deduction beats random/spam guessing.
- **Competitive:** opponent presence is felt without leaking private answers.
- **Replayable:** rematch is the natural next action.
- **Social:** private friendly play can later grow into party/team experiences.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Game Type | What is solved: `number`, `color`, later `word` |
| Match Mode | How play is organized: `practice`, `friendly`, later `ranked` |
| RuleSet | Validated machine-readable game and competition rules |
| Preset | Localized UX name/description pointing to a RuleSet version |
| Room | Reusable lobby/invite container that may host multiple matches |
| Match | One competition with frozen participants, rules, timing, and result |
| Challenge | One secret target assigned to one or more solvers |
| Guess | Submitted candidate input; it may be rejected |
| Attempt | Accepted, persisted, ordinal guess with feedback |
| Snapshot | Authorized current state for initial load/recovery |

## Scope decisions

### Social MVP (T0–T5)

- Number game
- Solo practice
- Private friendly 1v1
- Server-generated secret; 1v1 players solve the same challenge
- Guest-first identity
- Full lobby-to-rematch flow
- Realtime opponent activity, result, refresh, disconnect, and reconnect

### Expansion (T6–T7)

- Color Classic and Color Permutation
- Player-authored symmetric friendly duel
- Word feasibility prototype; implementation only after its gate passes

### Later

- Ranked, matchmaking, rating, leaderboard, progression
- 3–8 player party/team, spectator, tournament
- public room browser, chat, avatar upload, monetization

## Shared match behavior

### Supported initial flows

Solo skips lobby readiness and activates after creation/start. Friendly 1v1 uses:

```text
waiting -> ready_check -> countdown -> active -> finishing -> finished
    |           |                         |           |
    +-------> cancelled              abandoned     voided
```

- Rule changes before start reset every Ready state.
- Participants and the versioned RuleSet snapshot freeze before countdown.
- Late join is rejected after countdown begins.
- The server owns all timestamps and determines whether a command arrived in
  time.
- Active terminal transition rejects later guesses.
- Multiplayer timer does not pause on disconnect.
- Friendly disconnect has a working-default 30-second grace period, subject to
  playtest in T4.
- Room survives a completed match so participants can request a new Match.
- A rematch request expires after 60 seconds. The opponent accepts by requesting
  the same source Match, or explicitly declines. Acceptance creates entirely
  fresh Match state while keeping the Room and its members.

### History policy

RuleSets support:

```text
full
last_n(N)
none
```

The backend stores accepted Attempts according to its retention policy; history
policy controls what an authorized client may see during play.

### Invalid, repeated, and retried guesses

- Invalid format/rules: reject with a stable error; do not consume an Attempt.
- Same valid guess submitted intentionally again: allowed and consumes another
  Attempt; frontend warns before submission.
- Same command retransmitted with the same idempotency identity: return the
  original outcome; never create another Attempt.
- Abuse/rate counters may advance even when a Guess is invalid.

### Win and tie baseline

Working-default deduction-first ordering for the Social MVP:

1. Solved beats unsolved.
2. Fewer accepted Attempts wins.
3. Lower server-measured solve time breaks equal-attempt ties.
4. Equivalent finishes inside a configurable server tie window are a draw.

If neither player solves by deadline/attempt limit, the result is `unsolved`
or draw; MVP does not invent a "closest guess" winner.

Effective-time penalties and Final Guess are experiments, not MVP behavior.

### Opponent visibility

Visible during friendly play:

- display name and predefined avatar;
- connected/disconnected state;
- accepted attempt count;
- generic "opponent guessed" activity;
- playing/solved state.

Private during play:

- actual Secret;
- actual Guess;
- position feedback and guess history.

The reveal policy after a normal finish is part of the RuleSet. `voided` matches
do not automatically reveal protected data.

## Number game

### Rule fields

```text
sequence_length
allow_leading_zero
allow_duplicates
max_symbol_repetition
feedback_policy
history_policy
match_deadline_seconds
attempt_limit
```

Official MVP lengths are 5 and 6. The Domain represents secrets and guesses as
symbol sequences/strings, never integers. Both official presets allow duplicate
digits with maximum repetition two; leading zero is disabled. Exact preset
values are frozen in [the Phase 0 register](phase-0-decisions.md).

Unrestricted repetition and unique-only play remain experimental/custom rules,
not official MVP presets.

### Positional feedback

The semantic result for every guessed position is:

- `exact`: symbol exists at this position;
- `present`: an unconsumed instance exists elsewhere;
- `absent`: no unconsumed instance remains.

Evaluation is duplicate-safe:

1. mark and consume exact matches;
2. count unmatched secret symbols;
3. consume one remaining count for each present match;
4. mark all other positions absent.

Clients choose color/icon/text. Green/yellow/red are presentation defaults, not
API values.

The challenge solves only when every position is `exact`.

### Required examples

T0 must freeze an example matrix covering: all exact, all absent, mixed
position, repeated Guess against unique Secret, repeated Secret, leading zero,
invalid length, invalid character, repetition limit, and intentional duplicate
Attempt. These examples become shared contract fixtures.

## Color expansion

Color is one Game Type with RuleSet variants, not multiple engines.

Stable `color_id` is domain identity; Hex, localized label, pattern, shape, and
theme values are presentation metadata.

### Color Classic

- choose an ordered sequence from a known palette;
- configurable palette size and sequence length;
- duplicate-safe exact/present/absent evaluation;
- feedback may be positional or aggregate as an explicit policy.
- Official `color_classic_5_v1` uses 12 published colors, length 5, maximum
  repetition 2, aggregate feedback, full history, 180 seconds and 12 Attempts.

### Color Permutation

- player receives a known unique symbol set;
- every Guess must be a permutation of exactly that set;
- feedback returns only `exact_count` and never correct positions;
- default history is `last_n(1)`; `none` is a harder preset.
- Official `color_permutation_8_v1` uses the first 8 published palette entries,
  240 seconds and 15 Attempts.

"Hidden/Mystery Palette" is later. Do not call it "Blind" because that conflicts
with accessibility terminology.

Color is never the only cue: each palette entry must support a shape/icon/label
and sufficient contrast.

## Player-authored friendly duel expansion

This is distinct from a shared-secret race:

```text
Player A creates Challenge for B
Player B creates Challenge for A
server validates and commits both
both solve simultaneously after countdown
```

- A committed Secret is immutable and private from its solver.
- Room creation explicitly selects `challenge_source=players`; the default
  remains `system`. This option is Friendly 1v1 only.
- Setup lasts 120 seconds. Commit validates against the frozen RuleSet; the
  second Commit starts the shared countdown atomically.
- Setup timeout or participant leave cancels without Result, win, or loss.
- Creator sees only the same public progress allowed to an opponent.
- Results are Friendly-only and never rating-eligible because challenge
  difficulty differs.
- The Domain models separate Challenges; it must not assume one `Match.secret`.

## Word gate

Word is strategically interesting but not approved for MVP implementation.
T7 must prototype and decide:

- Persian normalization (`ی/ي`, `ک/ك`, spacing/half-space, diacritics);
- dictionary/inflection/proper-name policy;
- character-pool versus Wordle-like core loop;
- feedback semantics;
- profanity/harassment validation and appeal behavior;
- latency, false-accept, and false-reject thresholds.

AI moderation may assist later but cannot be the authoritative core validator.
T7's measured outcome is documented in
[the Word feasibility spike](word-feasibility-spike.md): production support is
NO-GO until its licensed-data, quality and moderation gates pass.

## Accessibility and localization

- API tokens and sequence indexes are locale-neutral.
- UI supports RTL and LTR without reversing logical sequence meaning.
- Touch, keyboard, screen reader, reduced motion, optional sound/haptic, and
  non-color cues are required client concerns.
- Invalid/success feedback must not depend only on animation or audio.

## Phase 0 status

Backend-facing decisions are frozen in
[the Phase 0 register](phase-0-decisions.md). Machine-readable contracts and
canonical examples live under `contracts/`. Product changes must update the
register, contract version, fixtures, and affected acceptance tests together.
