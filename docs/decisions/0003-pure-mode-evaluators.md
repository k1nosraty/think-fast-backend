# ADR-0003: Pure mode evaluators

- Status: Accepted
- Date: 2026-08-22

## Context

The modes share match flow but differ in validation and feedback. Embedding rules
in views, consumers, or ORM models would duplicate behavior and hinder testing.

## Decision

Represent each mode with a narrow deterministic evaluator operating on immutable
rules, a secret, and a guess. Evaluators return semantic feedback and contain no
Django, database, transport, random, or clock access.

## Consequences

Rules are easy to test and reuse. Application services must supply validated
inputs and perform persistence, authorization, timing, and event publication.
