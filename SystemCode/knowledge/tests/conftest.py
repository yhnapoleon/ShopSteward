import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def pg_sessions():
    url = os.getenv("KNOWLEDGE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("pending PostgreSQL: set KNOWLEDGE_TEST_DATABASE_URL (dedicated test DB)")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "shopsteward_knowledge_test":
        raise ValueError("tests require dedicated PostgreSQL database shopsteward_knowledge_test")
    url = parsed.set(drivername="postgresql+asyncpg")
    schema = "test_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        async with engine.begin() as connection:

            def migrate(sync_connection):
                cfg.attributes["connection"] = sync_connection
                command.upgrade(cfg, "head")

            await connection.run_sync(migrate)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
