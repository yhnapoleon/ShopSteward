import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent_bridge import models as agent_models  # noqa: F401
from app.alerts import models as alert_models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.execution import models as execution_models  # noqa: F401
from app.missions import models as mission_models  # noqa: F401
from app.operations import models as operations_models  # noqa: F401
from app.scheduling import models  # noqa: F401

settings = Settings()
if settings.database_url is None:
    raise RuntimeError("DATABASE_URL is required for migrations")
url = settings.database_url.get_secret_value()
target_metadata = Base.metadata


def migrate(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
        include_name=lambda name, type_, parents: type_ != "schema" or name in {None, "agent_data"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
