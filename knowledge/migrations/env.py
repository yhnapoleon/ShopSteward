"""Independent PostgreSQL migration chain, never run against the business database."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from shopsteward_knowledge.config import Settings
from shopsteward_knowledge.models import Base

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError("KNOWLEDGE_DATABASE_URL is required for migrations")
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        dialect_name="postgresql",
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    asyncio.run(online())
