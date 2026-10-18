"""Isolated development-only HTTP harness; never load application .env credentials."""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/tests/integration"))


async def main():
    import uvicorn
    from sqlalchemy.engine import make_url
    from test_missions import environment, headers
    from test_operations_cases import recovery_case

    from app.db.session import Database

    url = os.environ["TEST_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.host == "127.0.0.1" and parsed.database == "shopsteward_test"
    db = Database(url)
    async with environment(db) as (seed, client):
        case = await recovery_case(db, seed, client)
        # The unit helper's bare InboundRow deliberately lacks a full historical
        # Action. Browser reporting correctly rejects that incomplete fixture.
        # Use a separate complete browser scenario: demand on days 1-4, no old
        # inbound. B20 prevents 20 lost units; late C cannot recover those sales.
        from app.missions.models import InboundRow
        from app.operations.models import StockRow

        async with db.session() as session, session.begin():
            inbound = await session.get(InboundRow, ("original-" + seed["store_id"], "sku_001"))
            await session.delete(inbound)
            stock = await session.get(StockRow, (seed["store_id"], "sku_001"))
            stock.in_transit = 0
        daily = [
            dict(day, demand_qty=10 if i < 4 else 0) for i, day in enumerate(case["daily_demand"])
        ]
        response = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": case["current_revision"], "daily_demand": daily},
            headers=headers(),
        )
        assert response.status_code == 200
        app = client._transport.app
        for grant in app.state.settings.auth_tokens:
            if grant.principal_id == "operator":
                grant.roles = ["operator", "approver"]
        app.state.settings.source_stale_seconds = 3600
        fixture_file = ROOT / "var/next-phase-tests/browser-state.json"
        fixture_file.parent.mkdir(parents=True, exist_ok=True)
        fixture_file.write_text(
            json.dumps(
                {
                    "case_id": case["id"],
                    "store_id": case["store_id"],
                    "mission_id": case["mission_id"],
                }
            ),
            encoding="utf-8",
        )
        print("Isolated recovery HTTP fixture ready on 127.0.0.1:18000", flush=True)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=18000,
                lifespan="off",
                access_log=False,
                log_level="warning",
            )
        )
        await server.serve()
    await db.dispose()


asyncio.run(main())
