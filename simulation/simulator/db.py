from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Database:
    def __init__(self, url):
        self.engine = (
            create_async_engine(
                url, pool_pre_ping=True, connect_args={"timeout": 3, "command_timeout": 5}
            )
            if url
            else None
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False) if url else None

    def session(self):
        if self.sessions is None:
            raise OSError("Simulator database is not configured")
        return self.sessions()

    async def ready(self):
        async with self.session() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            await session.execute(text("SELECT id FROM simulation_runs LIMIT 0"))
            await session.execute(text("SELECT sequence FROM simulation_events LIMIT 0"))
            await session.execute(text("SELECT action_id FROM simulation_purchases LIMIT 0"))
            await session.execute(text("SELECT key FROM simulation_commands LIMIT 0"))
            return revision == "sim_0002_purchases"

    async def dispose(self):
        if self.engine:
            await self.engine.dispose()
