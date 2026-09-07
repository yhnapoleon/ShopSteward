from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.scheduling.models import Job


@dataclass(frozen=True)
class Handler:
    run: Callable[[Database, Job], Awaitable[Any]]
    retry_safe: bool = False
    apply: Callable[..., Awaitable[dict]] | None = None
    after_complete: Callable[..., Awaitable[None]] | None = None
    # Called before the claim transaction; owns its own short transactions.
    before_claim: Callable[[Database], Awaitable[None]] | None = None
    # Called after business rollback, inside the failure transaction. No HTTP.
    # Writes commit only if the runner's final failure transition owns the lease.
    on_error: Callable[[AsyncSession, Job, Exception], Awaitable[None]] | None = None


async def worker_probe(db: Database, job: Job) -> dict:
    async with db.session() as session:
        await session.execute(text("SELECT 1"))
    return {"summary": "Worker database probe completed", "references": []}


def make_handlers(settings):
    return {"worker_probe": Handler(worker_probe, retry_safe=True)}
