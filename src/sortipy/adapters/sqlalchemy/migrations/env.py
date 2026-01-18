"""Alembic environment configuration for Sortipy."""

from __future__ import annotations

import logging
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from sortipy.adapters.sqlalchemy import mapper_registry, start_mappers
from sortipy.config import get_database_config

config = context.config

if config.config_file_name is not None:
    config_path = Path(config.config_file_name)
    if config_path.suffix == ".ini" and config_path.exists():
        fileConfig(config.config_file_name)
    else:
        logging.basicConfig(level=logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)

log = logging.getLogger("alembic.env")

start_mappers()

target_metadata = mapper_registry.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = get_database_config().uri
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    existing_connection = config.attributes.get("connection")
    if existing_connection is not None:
        context.configure(
            connection=existing_connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()
        return

    main_url = get_database_config().uri
    engine = create_engine(
        main_url,
        # prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    cleanup = True

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
                compare_server_default=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        if cleanup:
            engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
