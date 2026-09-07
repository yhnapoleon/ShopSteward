"""Official PostgreSQL saver, dedicated connection and transaction for every write."""

from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row


class FencedPostgresSaver(BaseCheckpointSaver):
    def __init__(self, dsn, fence):
        super().__init__(serde=JsonPlusSerializer(pickle_fallback=False))
        self.dsn, self.fence = dsn, fence

    @asynccontextmanager
    async def connection(self):
        async with await psycopg.AsyncConnection.connect(
            self.dsn, autocommit=True, row_factory=dict_row, prepare_threshold=0
        ) as conn:
            await conn.execute("SET search_path TO agent_checkpoints, public")
            yield conn

    async def setup(self):
        async with self.connection() as conn:
            # Concurrent first starts must not race PostgreSQL system-catalog DDL.
            await conn.execute("SELECT pg_advisory_lock(73926011)")
            try:
                await conn.execute("CREATE SCHEMA IF NOT EXISTS agent_checkpoints")
                await AsyncPostgresSaver(conn, serde=self.serde).setup()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(73926011)")

    async def aget_tuple(self, config):
        async with self.connection() as conn:
            return await AsyncPostgresSaver(conn, serde=self.serde).aget_tuple(config)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        async with self.connection() as conn:
            async for item in AsyncPostgresSaver(conn, serde=self.serde).alist(
                config, filter=filter, before=before, limit=limit
            ):
                yield item

    async def aput(self, config, checkpoint, metadata, new_versions):
        async with self.connection() as conn:
            async with conn.transaction():
                await self.fence(conn)
                result = await AsyncPostgresSaver(conn, serde=self.serde).aput(
                    config, checkpoint, metadata, new_versions
                )
                await self.fence(conn)
                return result

    async def aput_writes(self, config, writes, task_id, task_path=""):
        async with self.connection() as conn:
            async with conn.transaction():
                await self.fence(conn)
                await AsyncPostgresSaver(conn, serde=self.serde).aput_writes(
                    config, writes, task_id, task_path
                )
                await self.fence(conn)

    def get_next_version(self, current, channel):
        return AsyncPostgresSaver.get_next_version(self, current, channel)
