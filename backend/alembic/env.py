#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Desc   : Alembic migration environment.
#
# Resolves the database URL from application settings (normalized to an async
# driver) when alembic.ini leaves ``sqlalchemy.url`` empty, so migrations target
# the same database the app uses. Supports both offline and online modes.

import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

import models
from alembic import context
from core.config import settings
from core.database import Base, db_manager
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Automatically import all ORM models so they register on Base.metadata.
for _, module_name, _ in pkgutil.iter_modules(models.__path__):
    importlib.import_module(f"{models.__name__}.{module_name}")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Use the URL from alembic.ini if set, else the app's (async-normalized) URL."""
    configured = (config.get_main_option("sqlalchemy.url") or "").strip().strip('"').strip("'")
    if configured:
        return db_manager._normalize_async_database_url(configured)
    return db_manager._normalize_async_database_url(settings.database_url)


def alembic_include_object(object, name, type_, reflected, compare_to):
    # type_ can be 'table', 'index', 'column', 'constraint'.
    # 'alembic_version' is managed by Alembic itself.
    if type_ == "table" and name in ["alembic_version"]:
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=alembic_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                include_object=alembic_include_object,
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda sync_conn: context.run_migrations())
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_migrations_online())
    except RuntimeError:
        asyncio.run(run_migrations_online())
