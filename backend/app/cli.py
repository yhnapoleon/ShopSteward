import argparse
import asyncio
import json
from uuid import uuid4

from app.core.config import Settings
from app.db.session import Database
from app.operations.repository import digest, get_state, store_for_run
from app.scheduling.repository import enqueue


async def execute(command, key, run_id=None, store_id=None):
    settings = Settings()
    db = Database(settings.database_url.get_secret_value() if settings.database_url else None)
    try:
        async with db.session() as session, session.begin():
            if command == "show-state":
                state = await get_state(session, store_id)
                print(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2))
                return
            if command == "sync-events":
                store = await store_for_run(session, run_id)
                job = await enqueue(
                    session,
                    job_type="sync_events",
                    store_id=store.id,
                    dedup_key=digest(["cli-sync", key]),
                    payload={"scenario_run_id": run_id},
                )
            else:
                job = await enqueue(session, job_type="worker_probe", dedup_key=key)
            print(job.id)
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local operator commands")
    parser.add_argument("command", choices=["enqueue-probe", "sync-events", "show-state"])
    parser.add_argument("--key", default=None, help="Reuse the same key to replay enqueue")
    parser.add_argument("--run-id")
    parser.add_argument("--store-id")
    args = parser.parse_args()
    if args.command == "sync-events" and not args.run_id:
        parser.error("sync-events requires --run-id")
    if args.command == "show-state" and not args.store_id:
        parser.error("show-state requires --store-id")
    asyncio.run(execute(args.command, args.key or str(uuid4()), args.run_id, args.store_id))
