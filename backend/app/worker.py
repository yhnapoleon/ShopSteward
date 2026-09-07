import argparse
import asyncio
import signal

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.scheduling.repository import heartbeat
from app.scheduling.runner import Runner


async def run(once: bool):
    settings = Settings()
    db = Database(settings.database_url.get_secret_value() if settings.database_url else None)
    configure_logging()
    try:
        if not await db.ready():
            raise RuntimeError("Run Alembic upgrade head before starting the worker")
        runner = Runner(db, settings)
        if once:
            await runner.run_once()
            async with db.session() as session, session.begin():
                await heartbeat(session, runner.worker_id, "STOPPED")
        else:
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            previous = {}
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous[sig] = signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
            try:
                await runner.serve(stop)
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the independent ShopSteward worker")
    parser.add_argument("--once", action="store_true", help="Process at most one registered job")
    args = parser.parse_args()
    asyncio.run(run(args.once))
