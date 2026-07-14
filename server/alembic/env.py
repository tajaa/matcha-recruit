import asyncio
import os
import re
import time
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from dotenv import load_dotenv

from alembic import context

# Load environment variables
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url with DATABASE_URL from environment
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Convert postgresql:// to postgresql+asyncpg:// for async
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # The asyncpg dialect takes ssl=, not libpq's sslmode= (which the URL
        # keeps for psql/pg_dump/asyncpg-raw compat; RDS rds.force_ssl=1
        # requires it).
        database_url = re.sub(r"([?&])sslmode=", r"\1ssl=", database_url)
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ORM models provide schema source of truth for autogenerate.
# Only tables with ORM models are managed — all 125 legacy tables are invisible.
from app.orm import Base
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Only manage tables that have ORM models. Prevents autogenerate from
    dropping or modifying unmodeled legacy tables."""
    if type_ == "table":
        return name in target_metadata.tables
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# Sentinel raised to abort a rehearsal. migrate-prod.sh matches on this exact
# string to tell "the migration ran clean" apart from "the migration failed".
REHEARSAL_MARKER = "MIGRATE_REHEARSAL"


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_name=include_name,
    )

    rehearsal = os.getenv("MIGRATE_REHEARSAL") == "1"

    # Online mode runs the whole upgrade in ONE transaction, so raising after
    # run_migrations() rolls back every revision in the run — the migration
    # executes against real rows, hits the constraints it would really hit, and
    # commits nothing. This is how a UniqueViolation in jparent01 was found on
    # prod data before prod. Elapsed time is part of the signal: a rehearsal that
    # crawls is a migration that is round-trip-bound and will hang over the tunnel.
    #
    # Caveat: rehearsal takes real locks and holds them until the rollback.
    with context.begin_transaction():
        started = time.monotonic()
        context.run_migrations()
        if rehearsal:
            elapsed = time.monotonic() - started
            # RuntimeError, not SystemExit: SystemExit is a BaseException and not
            # every context manager in the stack unwinds it the same way. The
            # abort must be boring and certain.
            raise RuntimeError(
                f"{REHEARSAL_MARKER}: rehearsal completed in {elapsed:.1f}s — "
                f"rolling back, nothing was committed."
            )


async def run_async_migrations():
    """Run migrations in 'online' mode with async support."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
