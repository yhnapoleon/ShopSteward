from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import AppError

SCHEMA_REVISION = "0006_periodic"


class Database:
    def __init__(self, url: str | None):
        self.engine = (
            create_async_engine(
                url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={"timeout": 3, "command_timeout": 5},
            )
            if url
            else None
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False) if url else None

    def session(self):
        if self._sessions is None:
            raise AppError(
                503, "DEPENDENCY_UNAVAILABLE", "Database is not configured", retryable=True
            )
        return self._sessions()

    async def ready(self) -> bool:
        async with self.session() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != SCHEMA_REVISION:
                return False
            await session.execute(text("SELECT id FROM job_runs LIMIT 0"))
            await session.execute(text("SELECT worker_id FROM worker_heartbeats LIMIT 0"))
            await session.execute(text("SELECT id FROM stores LIMIT 0"))
            await session.execute(text("SELECT scenario_run_id FROM source_cursors LIMIT 0"))
            await session.execute(text("SELECT id FROM missions LIMIT 0"))
            await session.execute(text("SELECT id FROM plans LIMIT 0"))
            await session.execute(text("SELECT id FROM alerts LIMIT 0"))
            await session.execute(text("SELECT id FROM actions LIMIT 0"))
            return True

    async def dispose(self):
        if self.engine is not None:
            await self.engine.dispose()
