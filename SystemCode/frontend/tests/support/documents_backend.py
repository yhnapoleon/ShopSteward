"""Isolated real K1 API for frontend transport tests; no worker, model, or development DB.

Set TEST_DATABASE_URL to the existing shopsteward_test database. Start from repo root.
Uses the backend's existing fixture helpers and auth identities, without invoking fixtures
that clean shared tables. Each run initializes only its own synthetic store.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(root / "backend"), str(root / "backend/tests/integration")]
from app.db.session import Database
from app.main import create_app
from test_missions import fresh_seed, settings
from test_operations import initialize


async def main():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    assert url.database == "shopsteward_test" and url.host in ("127.0.0.1", "localhost")
    database = Database(url.render_as_string(hide_password=False))
    assert await database.ready(), "Migrate the dedicated test DB before running"
    seed = fresh_seed()
    await initialize(database, seed)
    output = root / "var/documents-http"
    output.mkdir(parents=True, exist_ok=True)
    (output / "context.json").write_text(json.dumps({"store_id": seed["store_id"]}))
    config = settings(
        database,
        seed,
        agent_enabled=False,
        knowledge_storage_root=str(output / seed["store_id"]),
    )
    app = create_app(config)
    await database.dispose()
    print(
        "Isolated document API ready on 127.0.0.1:8018; development DB untouched",
        flush=True,
    )
    await uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8018, log_level="warning")
    ).serve()


if __name__ == "__main__":
    asyncio.run(main())
