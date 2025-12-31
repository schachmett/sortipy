# Database Policy

This document captures how Sortipy interacts with relational storage and how agents should manage database schema changes.

## Configuration
- Runtime adapters obtain the database URI through `sortipy.common.storage.get_database_uri()`, which honours `DATABASE_URI` (preferred for deployments) or falls back to the platform-specific default file location inside `SORTIPY_DATA_DIR`.
- Local tooling such as Alembic reads the same value. When invoking the CLI directly, set `ALEMBIC_CONFIG=pyproject.toml` (already included in the recommended `.env`) so Alembic loads the project configuration from `[tool.alembic]`.
- Tests should continue to override the URI explicitly when they need isolated in-memory databases; never hard-code absolute paths.

## Migrations
- Alembic scaffolding lives in `src/sortipy/adapters/sqlalchemy/migrations/`. The helper functions in `__init__.py` construct an Alembic `Config` from `pyproject.toml`, so handlers inside application code can call `upgrade_head(engine=...)` and share the existing SQLAlchemy engine.
- `env.py` is the environment hook that Alembic executes for each migration command. It ensures SQLAlchemy mappers are configured, resolves a database URL with `get_database_uri()` when the CLI command does not supply one, and executes migrations using either the already-configured adapter engine or a temporary engine built from the project settings.
- `script.py.mako` is the template used when generating new revision files. Alembic copies it into `versions/` and fills in metadata such as `revision`, `down_revision`, and the migration docstring header, giving us a consistent function skeleton for `upgrade()` and `downgrade()`.
- To generate a new migration: `ALEMBIC_CONFIG=pyproject.toml alembic revision --autogenerate -m "describe change"`. Apply migrations with `ALEMBIC_CONFIG=pyproject.toml alembic upgrade head`, or call `sortipy.adapters.sqlalchemy.migrations.upgrade_head()` from Python.
- The first committed revision (`822b044566e8_baseline_schema.py`) reflects the current schema baseline. When upgrading an existing local database for the first time, back it up and run `ALEMBIC_CONFIG=pyproject.toml alembic stamp 822b044566e8 && ALEMBIC_CONFIG=pyproject.toml alembic upgrade head` to mark and apply the baseline safely.

## Maintenance Notes
- Any structural database change must be accompanied by an Alembic revision. Avoid calling `create_all_tables()` in production paths once migrations are active; rely on `upgrade_head()` instead.
- When you modify `pyproject.toml` entries under `[tool.alembic]`, ensure they remain compatible with both the CLI workflow and the in-process helper. Update this policy document if new required environment variables are introduced.
