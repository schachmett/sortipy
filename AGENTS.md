# Agent Workflow Notes

_Read this first: these notes are for automation agents working in this repository. They highlight the expectations, required tools, and canonical references to consult before making changes._

_Staleness guard: if the tooling, frameworks, or policies referenced here drift from reality, pause and notify the maintainers (or add an item to `docs/todo.md`) so we can refresh this document._

## Quickstart Checklist
- Prefer editor-style patch operations (`apply_patch` or equivalent) for edits; reach for shell commands only when a scripted workflow is unavoidable.
- Run `uv run poe fix` for auto-fixes, then `uv run poe lint`, `uv run poe typecheck` and, if reasonable `uv run poe test` before handing work off.
- Before attempting manual lint fixes, ensure that `uv run poe fix` was run.
- If a required tool/command is missing or blocked, stop and ask the user rather than guessing.
- Do not introduce new runtime or development dependencies without explicit user approval; confirm intent before touching `pyproject.toml`.
- Escalate blockers instead of weakening domain invariants or bypassing documented policies.

## Key References
- [ADR-0001](docs/adr/0001-architecture-style.md) ports-and-adapters boundaries.
- [ADR-0002](docs/adr/0002-domain-model.md) canonical domain entities and relationships.
- [ADR-0003](docs/adr/0003-persistence-mapping.md) SQLAlchemy adapter strategy.
- [ADR-0004](docs/adr/0004-ingestion-strategy.md) pull-based ingestion cadence.
- [ADR-0005](docs/adr/0005-configuration-management.md) dotenv-based configuration approach.
- [ADR-0006](docs/adr/0006-ui-adapters.md) CLI as the current primary adapter.
- [Logging policy](docs/policies/logging.md) for log levels, style, and scope.
- [Testing policy](docs/policies/testing.md) for required test coverage and isolation.
- [User stories index](docs/user-stories/index.md) for product expectations.
- [docs/todo.md](docs/todo.md) for outstanding technical work and upcoming migrations.

## Tooling & Configuration
- Use `uv` (`uv sync --group dev`, `uv run ...`) so results match CI and pre-commit.
- Repository configuration (formatter, linter, type-checker settings) lives in `pyproject.toml`.
- Follow `docs/policies/typing.md` for guidance on how to use protocols, casts, and `TYPE_CHECKING` blocks when adding typed code.
- Follow `docs/policies/logging.md` when emitting new log statements; avoid `print`.
- Handle secrets through `.env` files per ADR-0005; never commit secrets.

## Design Principles & Invariants
- Maintain the ports-and-adapters layering (ADR-0001); domain code depends only on domain-defined ports.
- Preserve the canonical domain model and relationships (ADR-0002); adapters perform provider-to-domain translation.
- Keep persistence concerns inside SQLAlchemy adapters (ADR-0003); domain entities remain framework-free.
- Keep ingestion idempotent and checkpointed (ADR-0004); respect rate limits and retry guidance.
- Prefer pure functions within the domain and centralize business rules in domain services; push side effects to adapters.
- Do not weaken invariants for convenience: validated domain entities, unique identifiers, transactional updates, and idempotent ingestion are non-negotiable—escalate if they block you.
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes, verbs for behavior, nouns for types and adapters.

## Framework & Adapter Notes
- SQLAlchemy is the chosen ORM (ADR-0003); plan migrations with Alembic as tracked in `docs/todo.md`.
- The CLI remains the primary UI (ADR-0006); new interfaces must call domain ports rather than domain internals.
- Ingestion remains pull-based (ADR-0004); adapters must log checkpoints and handle backoff.
- Configuration currently flows through dotenv-loaded settings (ADR-0005); introducing alternatives requires a new ADR.

## Process Reminders
- Keep worktrees clean: do not create commits without user direction, stage only what belongs to the current proposal.
- Before running `git commit`, ask the user for explicit approval in this session.
- When drafting commit messages, use conventional scope keywords (`feat`, `bugfix`, `docs`, `test`, `tooling`, `refactor`, `chore`, etc.) followed by a concise summary so history stays scannable.
- Seek guidance instead of forcing changes past failing quality gates.
- When a feature or fix feels release-ready, suggest a semantic-version git tag and explain the milestone’s value.
- After one failed lint/typing fix attempt, hand control back to the user; don't keep iterating
