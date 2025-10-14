# Testing Policy

This policy defines the minimum testing expectations for Sortipy contributors.

## Scope
- Applies to all pull requests and automated agent contributions.
- Covers unit tests, adapter-layer integration tests, and database-backed tests.

## Principles
- Place tests alongside the code they validate (`tests/domain`, `tests/adapters`, etc.).
- Keep tests deterministic and isolated; never call live external services.

## Test Types
- **Unit tests** exercise pure domain logic with in-memory fakes or mocks of domain ports.
- **Adapter tests** verify adapter implementations against contract tests, using stubbed external responses.
- **Database tests** run against the local fixtures in `tests/fixtures/`, resetting state between cases.

## Expectations
- Provide at least one positive path, one representative failure, and one relevant edge case for new behavior.
- Maintain or improve coverage; target ≥80% module coverage where practical, and never drop coverage for touched files without approval.
- Use shared fixtures from `tests/conftest.py` rather than inventing new patterns without discussion.

## Tooling
- Run `.venv/bin/pytest` locally (or via the pre-commit hook) before requesting review.
- Adopt VCR/fake clients for HTTP interactions to keep tests offline.

## Escalation
- Treat persistent flaky behavior as a defect: capture reproduction steps and raise it instead of weakening assertions or muting tests.
