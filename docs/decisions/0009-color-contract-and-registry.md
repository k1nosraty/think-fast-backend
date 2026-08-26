# ADR 0009 — Color contracts and explicit game registry

**Status:** Accepted in T6 on 2026-08-26

## Decision

- Color uses arrays of stable `color_id` values in Guess, Secret reveal and
  private Attempt history. Hex values are presentation metadata, never identity.
- Every palette entry publishes `color_id`, hex, localization key, shape and
  pattern so color is not the only cue.
- `color_classic_5_v1` selects five symbols from the twelve-color palette,
  allows at most two occurrences, uses aggregate exact/present feedback, full
  history, 180 seconds and 12 Attempts.
- `color_permutation_8_v1` uses the first eight palette symbols exactly once,
  returns only `exact_count`, shows only the latest Attempt, allows 240 seconds
  and 15 Attempts.
- Number and Color implement one narrow explicit adapter contract registered by
  stable `game_type`. Match orchestration is shared and does not branch by game.
- Accepted Attempts now store JSON so Number strings and Color arrays retain
  their native contract shape. Migration 0007 preserves existing Number text.

## Consequences

Both Color variants reuse Solo, Room, Match, realtime, recovery, rematch and
analytics behavior. Adding another game requires an explicit adapter and
versioned contracts; this is not a generic plugin framework.
