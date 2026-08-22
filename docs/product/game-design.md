# Game Design Specification

## Product premise

Think Fast is a deduction race. A player repeatedly submits an ordered guess,
receives limited feedback, and tries to solve the secret with fewer attempts or
in less time than opponents. The same platform supports solo practice, direct
duels, and small multiplayer rooms.

## Canonical terminology

- **Game mode:** evaluation rule family, such as Number Code.
- **Rule configuration:** immutable parameters for one match (length, palette,
  duplicate policy, history visibility, limits).
- **Room:** lobby and access boundary for multiplayer participants.
- **Match:** one competitive session under a frozen rule configuration.
- **Round:** one secret-solving contest within a match.
- **Secret:** authoritative ordered sequence being solved.
- **Attempt:** one validated guess from one participant.
- **Feedback:** mode-specific result of evaluating an attempt.

## Shared match variants

- **Solo practice:** one player versus a server-generated secret.
- **Shared-secret race:** the server generates one secret for all players. This
  is the recommended competitive default because difficulty is identical.
- **Player-authored duel:** each player commits a valid secret for an opponent
  before either secret is revealed. This should arrive after the core MVP.
- **Multiplayer room:** 2–8 players by initial product policy; capacity is a rule
  setting, not a hardcoded evaluator assumption.

## Shared configurable rules

- Sequence length and allowed symbols
- Whether symbols may repeat
- Maximum attempts and optional round deadline
- History policy: `full`, `latest_only`, or `none`
- Win policy: first correct guess, lowest attempts, fastest elapsed time, or a
  configured composite
- Feedback presentation mapping (semantic values remain stable)
- Whether the secret/palette is server-generated or player-authored

Rule configuration is frozen when a match starts. A client may display rules,
but cannot change them during play.

## Mode 1 — Number Code

### Default rules

- Length: 5 or 6 digits; recommended competitive default is 6.
- Alphabet: digits `0`–`9`.
- Repetition: disabled by default.
- Leading zero: disabled by default to avoid ambiguity between a number and a
  fixed-width code. It may later be enabled explicitly, in which case values
  are always strings.

### Feedback

Feedback is position-preserving: one semantic result is returned for each
guessed digit.

- `exact` (green): digit exists at this position.
- `present` (yellow): digit exists elsewhere.
- `absent` (red): digit is not available elsewhere in the secret.

If repeats are ever enabled, evaluation must use a two-pass consumption
algorithm: mark exact matches first, then match remaining symbols by remaining
frequency. This prevents over-reporting duplicate guesses.

### Completion

The attempt solves the round only when every position is `exact`.

## Mode 2 — Hidden Color Code

Players guess an ordered sequence drawn from a configured palette (for example,
12 unique available colors). Sequence length and palette size are distinct.

The rule engine returns semantic feedback, not UI glyphs:

- `exact`
- `present`
- `absent`

The initial presentation maps them to `+`, `-`, and `0`; clients may render
equivalent accessible shapes/text. The API must never use color alone to convey
meaning.

Default repetition is disabled. If enabled later, the same two-pass frequency
rule as Number Code applies.

## Mode 3 — Color Permutation

Players reorder a fixed set of unique colors to discover the target ordering.

### Variants

- **Known palette:** all colors in the target are shown at the start; players
  submit permutations of exactly those colors. Recommended default.
- **Hidden palette:** players know only sequence length and choose from a larger
  configured palette. This is materially harder and should be a distinct rule
  variant, not a UI-only switch.

### Feedback

Return only `exact_count`, the number of symbols in their correct positions.
Do not reveal which positions are correct. Guess history defaults to `none` in
this mode, though the match configuration may choose another policy.

For the known-palette variant, every guess must be a permutation of the offered
symbols: no missing, additional, or repeated colors.

## Match lifecycle

```text
draft -> lobby -> ready -> active -> completed
                    |         |          ^
                    v         v          |
                 cancelled  abandoned ---
```

- A solo match may skip `lobby` and `ready`.
- Participant membership and rules freeze on transition to `active`.
- The server records start/deadline timestamps and decides whether an attempt is
  in time.
- Terminal matches reject further guesses.
- Reconnect returns an authorized state snapshot; events alone are not state.

## Ranking and ties

Recommended MVP race ranking:

1. Solved beats unsolved.
2. Fewer valid attempts wins.
3. Lower server-measured elapsed time breaks equal-attempt ties.
4. Guesses committed within a small configured tie window with the same attempt
   count are declared tied, avoiding network-latency theater.

Exact tie-window and timeout values remain product configuration and must be
load-tested before launch.

## Validation and fairness

- Normalize and validate every guess against the frozen rule configuration.
- Reject invalid guesses without consuming an attempt unless abuse policy says
  otherwise.
- Give an idempotency key to guess commands so retries cannot create attempts.
- Use server time and transactional sequence numbers for ordering.
- Generate secrets with a cryptographically secure random source.
- Never send a secret before authorized post-round reveal.
- A player-authored secret must be committed before play, stored protected, and
  never visible to its solver.

## Accessibility and localization

- Every color has a stable identifier and localized display label.
- Feedback includes semantic text/shape; color is supplemental.
- API values are locale-neutral; translation happens at presentation boundaries.
- Support right-to-left clients without reversing the logical sequence indexes.

## MVP scope

The backend MVP proves Solo Number Code first, then private shared-secret rooms,
then Modes 2 and 3. Public matchmaking, rankings, chat, tournaments, and economy
features are deliberately excluded until core retention and fairness are known.

## Product questions to validate before public launch

- Target match duration and ideal maximum attempts per mode
- Whether competitive ranking prioritizes attempts or time
- Exact tie window and reconnect grace period
- Default history policy per difficulty tier
- Whether player-authored secrets are private-room-only
- Age rating, display-name policy, retention period, and regional privacy needs
