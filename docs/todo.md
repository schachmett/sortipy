# TODOs

- [x] Wire up pre-commit hooks that run `.venv/bin/ruff check`, `.venv/bin/pyright`, and `.venv/bin/pytest`.
- [x] Define logging policy (levels, destinations) and document expectations for agents (`docs/policies/logging.md`).
- [ ] Add structured logging to sync orchestration and adapters.
- [ ] Establish an issue-tracking workflow accessible to both user and agent (no external GitHub reliance).
- [ ] Introduce database migrations (e.g. Alembic) so schema changes apply across existing installs.
