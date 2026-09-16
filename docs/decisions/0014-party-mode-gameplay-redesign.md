# 0014. Party Mode Core Gameplay Redesign

Date: 2026-09-16
Status: Accepted

## Context

The previous friendly room architecture attempted to generalize 2-player player-authored duel concepts (symmetric pairwise secret generation) or single-match duels across larger groups. For 3–8 players sitting together in a party environment, an $N \times N$ secret exchange created unacceptable configuration complexity, slow match startup, and confusing player-to-player relationships.

## Decision

We redesign the core social experience into **Party Mode (1 Creator $\to$ Multiple Guessers)**:

1. **Star Topology**:
   - In each round, exactly one player is the **Creator**, who manually inputs the secret.
   - All other room participants are **Guessers**, attempting to deduce the identical secret simultaneously.
2. **Server-Authoritative Evaluation and Zero-Leak Privacy**:
   - The creator's secret is stored encrypted in the backend `protected_secret` field.
   - Each guesser receives private positional feedback on their personal WebSocket channel.
   - Opponent guesses, attempts, and feedback are never serialized to other players until the round concludes.
   - When a player solves, the server emits a lightweight `party.player_solved` notification containing only the solver's identity and placement.
3. **Short Authoritative Timers**:
   - Single authoritative 60-second countdown managed on the backend. Submissions after deadline expiration are rejected with `deadline_elapsed`.
4. **Intuitive Party Scoring**:
   - Guessers receive speed/rank rewards: 1st (+100), 2nd (+75), 3rd (+50), remaining (+25).
   - The Creator receives difficulty points based on group performance (+80 if completely unsolved, +20 per unsolved guesser).
5. **Fair Creator Rotation**:
   - Rounds rotate the Creator role in a fair round-robin order.
   - Disconnected or leaving players are gracefully bypassed without aborting the match.
6. **Multi-Round Matches & Rematch**:
   - Matches support 3, 5, or 7 rounds with cumulative scoring, followed by an end-of-match podium and 1-click Rematch.
7. **Isolation of Modes**:
   - Solo Practice and 2-Player Duel modes remain completely functional and isolated.
   - Persian Word Mode remains an isolated prototype until authoritative dictionary licensing is finalized.

## Consequences

- Multiplayer party gameplay is understandable within seconds.
- Match setup requires zero complex configurations.
- Full test coverage guarantees zero leaks of secrets or opponent attempts.
