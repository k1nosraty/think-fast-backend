# Contributing

## Workflow

1. Select a scoped roadmap item and write acceptance criteria.
2. Confirm the owning application and whether an ADR is needed.
3. Implement the smallest vertical change with tests.
4. Update API/product documentation when behavior changes.
5. Run the project quality gates before requesting review.

## Intended quality gates

The exact tooling is selected in Roadmap Phase 1. The baseline will include:

- Ruff formatting and linting
- mypy with Django typing support
- pytest and pytest-django
- Django system checks and migration consistency checks
- OpenAPI schema validation

## Commit style

Use focused imperative commits, for example:

```text
feat(games): add number-code evaluator
test(matches): cover simultaneous winning guesses
docs(api): define reconnect snapshot event
```

## Definition of done

A change is complete when behavior is tested, public contracts are documented,
security/privacy effects are considered, and no unrelated refactor is bundled.
