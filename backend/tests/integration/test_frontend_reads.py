"""Frontend reads must preserve authorization, accounting and snapshot boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from test_execution import Supplier, approve, execute, isolated_actions, planned  # noqa: F401
from test_missions import clean_queue, environment, fresh_seed, headers  # noqa: F401
from test_operations import event, ingest, initialize, state

pytestmark = pytest.mark.integration


async def get(client, path, **params):
    response = await client.get("/api/v1/" + path, params=params, headers=headers("viewer"))
    assert response.status_code == 200, response.text
    return response.json()


async def test_current_environment_tracks_successful_creation_not_completion_or_page(db):
    from uuid import uuid4

    from app.scheduling.repository import enqueue

    async with environment(db) as (seed, client):
        other = fresh_seed()
        await initialize(db, other)

        async def creation(store_id, age, status):
            async with db.session() as session, session.begin():
                job = await enqueue(
                    session, job_type="initialize_scenario", dedup_key=str(uuid4()), payload={}
                )
                job.created_at = datetime.now(UTC) + timedelta(seconds=age)
                job.status = status
                job.result = {"references": [{"type": "store", "id": store_id}]}
                return job.id

        await creation(other["store_id"], 0, "SUCCEEDED")
        newest = await creation(seed["store_id"], 10, "READY")
        # An unimported/pending environment must not replace the live one.
        assert (await get(client, "stores"))["active_store"] is None
        async with db.session() as session, session.begin():
            await session.execute(
                text("UPDATE job_runs SET status='SUCCEEDED' WHERE id=:id"), {"id": newest}
            )
        assert (await get(client, "stores"))["active_store"]["store_id"] == seed["store_id"]
        # A late result for an older request cannot switch the environment backwards.
        await creation(other["store_id"], -10, "SUCCEEDED")
        await creation(other["store_id"], 20, "FAILED")
        page = await client.get("/api/v1/stores?limit=1", headers=headers("admin"))
        assert page.json()["active_store"]["store_id"] == seed["store_id"]
        # Current-environment metadata never leaks a store outside the caller's scope.
        await creation(other["store_id"], 30, "SUCCEEDED")
        assert (await get(client, "stores"))["active_store"] is None


async def test_identity_and_store_discovery_are_scoped(db):
    async with environment(db) as (seed, client):
        other = fresh_seed()
        await initialize(db, other)
        assert await get(client, "me") == {
            "principal_id": "viewer",
            "roles": ["viewer"],
            "store_scope": "ASSIGNED",
        }
        stores = await get(client, "stores")
        assert [item["store_id"] for item in stores["items"]] == [seed["store_id"]]
        assert stores["next_cursor"] is None
        assert (await client.get("/api/v1/me")).status_code == 401
        page = await client.get("/api/v1/stores?limit=1", headers=headers("admin"))
        assert page.status_code == 200
        cursor = page.json()["next_cursor"]
        assert cursor is not None
        wrong = await client.get(
            "/api/v1/stores", params={"cursor": cursor}, headers=headers("viewer")
        )
        assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "INVALID_CURSOR"
        for path in ["sales", "actions", "inbounds", "ledger-entries"]:
            denied = await client.get(
                "/api/v1/" + path, params={"store_id": other["store_id"]}, headers=headers("viewer")
            )
            assert denied.status_code == 404


async def test_sales_paging_dates_and_summary_use_distinct_recorded_facts(db):
    async with environment(db) as (seed, client):
        first = event(seed, quantity=2)
        second = event(seed, 2, quantity=3, unit_price_minor=3000)
        first.update(simulation_time="2026-09-08T23:59:59Z", occurred_at="2026-09-09T01:00:00Z")
        second.update(simulation_time="2026-09-09T00:00:00Z", occurred_at="2026-09-08T01:00:00Z")
        await ingest(db, seed, [first, second])
        await ingest(db, seed, [first, second])
        params = {"store_id": seed["store_id"], "limit": 1}
        page = await get(client, "sales", **params)
        assert [r["event_id"] for r in page["items"]] == [second["event_id"]]
        assert page["items"][0]["sales_amount_minor"] == 9000
        following = await get(client, "sales", **(params | {"cursor": page["next_cursor"]}))
        assert [r["event_id"] for r in following["items"]] == [first["event_id"]]
        assert following["next_cursor"] is None
        interval = {
            "store_id": seed["store_id"],
            "from": "2026-09-08T08:00:00+08:00",
            "to": "2026-09-10T00:00:00Z",
        }
        summary = await get(client, "sales/summary", **interval)
        assert (
            summary["record_count"],
            summary["recorded_quantity"],
            summary["recorded_sales_amount_minor"],
        ) == (2, 5, 13000)
        assert summary["coverage"] == "RECORDED_EVENTS_ONLY"
        assert [b["recorded_quantity"] for b in summary["buckets"]] == [2, 3]
        only_first = await get(client, "sales", **(interval | {"to": "2026-09-09T00:00:00Z"}))
        assert [r["event_id"] for r in only_first["items"]] == [first["event_id"]]
        for extra in [
            {"from": interval["from"]},
            {"warehouse_id": "invented"},
            {"cursor": ""},
            {"from": "2026-01-01T00:00:00Z", "to": "2026-09-10T00:00:00Z"},
        ]:
            result = await client.get(
                "/api/v1/sales",
                params={"store_id": seed["store_id"]} | extra,
                headers=headers("viewer"),
            )
            assert result.status_code == 422, result.text
        changed = await client.get(
            "/api/v1/sales",
            params=params | {"sku_id": "sku_001", "cursor": page["next_cursor"]},
            headers=headers("viewer"),
        )
        assert changed.status_code == 422


async def test_purchase_reads_separate_acceptance_arrival_and_unique_ledger(db):
    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        await execute(db, seed, supplier)
        action_id = accepted["action_id"]
        actions = await get(client, "actions", store_id=seed["store_id"], status="SUCCEEDED")
        detail = await get(client, "actions/" + action_id)
        assert actions["items"] == [detail]
        inbound = (await get(client, "inbounds", store_id=seed["store_id"]))["items"][0]
        assert (
            inbound["ordered_quantity"],
            inbound["received_quantity"],
            inbound["remaining_quantity"],
            inbound["arrival_status"],
        ) == (40, 0, 40, "NOT_RECEIVED")
        goods = event(seed, 1, "GOODS_RECEIVED", action_id=action_id, quantity=10)
        await ingest(db, seed, [goods])
        await ingest(db, seed, [goods])
        inbound = (
            await get(
                client, "inbounds", store_id=seed["store_id"], arrival_status="PARTIALLY_RECEIVED"
            )
        )["items"][0]
        assert (inbound["received_quantity"], inbound["remaining_quantity"]) == (10, 30)
        assert (
            await get(client, "inbounds", store_id=seed["store_id"], arrival_status="RECEIVED")
        )["items"] == []
        ledger = await get(client, "ledger-entries", store_id=seed["store_id"])
        assert [r["effect_type"] for r in ledger["items"]] == [
            "GOODS_RECEIVED",
            "PURCHASE_ACCEPTED",
            "INIT",
        ]
        purchase = ledger["items"][1]
        assert purchase["changes"] == {
            "cash_delta_minor": -40000,
            "receivables_delta_minor": 0,
            "on_hand_delta": 0,
            "in_transit_delta": 40,
        }
        assert purchase["simulation_time"] is None
        assert purchase["action_id"] == action_id
        assert ledger["items"][2]["opening_state"]["cash_minor"] == 100000
        goods_only = await get(
            client,
            "ledger-entries",
            store_id=seed["store_id"],
            effect_type="GOODS_RECEIVED",
            limit=1,
        )
        assert [row["effect_type"] for row in goods_only["items"]] == ["GOODS_RECEIVED"]
        first_page = await get(client, "ledger-entries", store_id=seed["store_id"], limit=1)
        second_page = await get(
            client,
            "ledger-entries",
            store_id=seed["store_id"],
            limit=1,
            cursor=first_page["next_cursor"],
        )
        third_page = await get(
            client,
            "ledger-entries",
            store_id=seed["store_id"],
            limit=1,
            cursor=second_page["next_cursor"],
        )
        assert [
            page["items"][0]["effect_type"] for page in [first_page, second_page, third_page]
        ] == ["GOODS_RECEIVED", "PURCHASE_ACCEPTED", "INIT"]
        assert third_page["next_cursor"] is None
        assert (await get(client, "actions", store_id=seed["store_id"], status="FAILED"))[
            "items"
        ] == []
        assert len(supplier.calls) == 1
        invalid = await client.get(
            "/api/v1/inbounds",
            params={"store_id": seed["store_id"], "mission_id": "missing"},
            headers=headers("viewer"),
        )
        assert invalid.status_code == 404
        assert mission["id"] == inbound["mission_id"]


async def test_all_reads_are_business_read_only_and_keep_stale_facts(db):
    from app.operations.models import SourceCursor

    async with environment(db) as (seed, client):
        await ingest(db, seed, [event(seed, quantity=1)])
        async with db.session() as session, session.begin():
            cursor = await session.get(SourceCursor, seed["scenario_run_id"])
            cursor.last_success_at = datetime.now(UTC) - timedelta(hours=1)
        tables = [
            "business_events",
            "ledger_entries",
            "job_runs",
            "command_receipts",
            "alerts",
            "mission_timeline",
        ]

        async def counts():
            async with db.session() as session:
                return [
                    await session.scalar(text("SELECT count(*) FROM " + table)) for table in tables
                ]

        before_counts, before_state = await counts(), await state(db, seed)
        for _ in range(2):
            await get(client, "me")
            await get(client, "stores")
            for path in ["sales", "actions", "inbounds", "ledger-entries"]:
                result = await get(client, path, store_id=seed["store_id"])
                assert result["context"]["freshness"]["status"] == "STALE"
            await get(
                client,
                "sales/summary",
                **{
                    "store_id": seed["store_id"],
                    "from": "2026-09-01T00:00:00Z",
                    "to": "2026-09-20T00:00:00Z",
                },
            )
        assert await counts() == before_counts
        assert await state(db, seed) == before_state


async def test_cancelled_mission_keeps_unknown_purchase_and_later_inbound_visible(db):
    from test_execution import retry_now

    async with environment(db) as (seed, client):
        mission, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        supplier = Supplier()
        supplier.drop_response = True
        await execute(db, seed, supplier)
        current = await get(client, "missions/" + mission["id"])
        cancelled = await client.post(
            f"/api/v1/missions/{mission['id']}/control",
            json={"operation": "cancel", "expected_mission_version": current["mission_version"]},
            headers=headers("approver"),
        )
        assert cancelled.status_code == 200, cancelled.text
        params = {"store_id": seed["store_id"], "mission_id": mission["id"]}
        pending = await get(client, "actions", **params, status="UNKNOWN")
        assert [row["id"] for row in pending["items"]] == [accepted["action_id"]]
        assert (await get(client, "inbounds", **params))["items"] == []
        supplier.drop_response = False
        await retry_now(db, accepted["action_id"])
        await execute(db, seed, supplier)
        inbounds = await get(client, "inbounds", **params)
        assert inbounds["items"][0]["action_id"] == accepted["action_id"]
        assert inbounds["items"][0]["remaining_quantity"] == 40
        assert (await get(client, "actions", **params, status="SUCCEEDED"))["items"][0][
            "id"
        ] == accepted["action_id"]


async def test_read_context_and_sales_share_one_database_snapshot(db, monkeypatch):
    from app.reporting import read_repository

    async with environment(db) as (seed, client):
        original = read_repository.read_context
        committed = False

        async def concurrent_commit(*args, **kwargs):
            nonlocal committed
            result = await original(*args, **kwargs)
            if not committed:
                committed = True
                # A separate connection commits after the reader acquired its snapshot.
                await ingest(db, seed, [event(seed, quantity=2)])
            return result

        monkeypatch.setattr(read_repository, "read_context", concurrent_commit)
        first = await get(client, "sales", store_id=seed["store_id"])
        assert first["context"]["state_version"] == 1
        assert first["context"]["source_sequence"] == 0
        assert first["items"] == []
        second = await get(client, "sales", store_id=seed["store_id"])
        assert second["context"]["state_version"] == 2
        assert second["context"]["source_sequence"] == 1
        assert second["items"][0]["quantity"] == 2


async def test_corrupt_stored_sales_fail_explicitly_without_payload_leak(db):
    from app.operations.models import EventRow

    async with environment(db) as (seed, client):
        sale = event(seed, quantity=2)
        await ingest(db, seed, [sale])
        async with db.session() as session, session.begin():
            row = await session.get(EventRow, (seed["scenario_run_id"], sale["event_id"]))
            row.document = row.document | {"simulation_time": "invalid-private-content"}
        result = await client.get(
            "/api/v1/sales", params={"store_id": seed["store_id"]}, headers=headers("viewer")
        )
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "INVALID_STORED_DATA"
        assert result.json()["error"]["retryable"] is False
        assert "invalid-private-content" not in result.text


async def test_empty_roles_and_service_identity_and_unknown_queries(db):
    from uuid import uuid4

    import httpx
    from test_missions import settings

    from app.core.config import TokenGrant
    from app.main import create_app
    from app.scheduling.repository import enqueue

    seed = fresh_seed()
    await initialize(db, seed)
    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="initialize_scenario", dedup_key=str(uuid4()))
        job.status = "SUCCEEDED"
        job.result = {"references": [{"type": "store", "id": seed["store_id"]}]}
    config = settings(db, seed)
    config.auth_tokens.extend(
        [
            TokenGrant(
                token="frontend-empty-credential-00001",
                principal_id="empty",
                store_ids=[seed["store_id"]],
            ),
            TokenGrant(
                token="frontend-service-credential-01", principal_id="service", kind="service"
            ),
        ]
    )
    app = create_app(config)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        empty = {"Authorization": "Bearer frontend-empty-credential-00001"}
        me = await client.get("/api/v1/me", headers=empty)
        assert me.json()["roles"] == []
        assert (await client.get("/api/v1/stores", headers=empty)).json()["items"] == []
        assert (await client.get("/api/v1/stores", headers=empty)).json()["active_store"] is None
        for path in [
            "me",
            "stores",
            "sales",
            "sales/summary",
            "actions",
            "inbounds",
            "ledger-entries",
        ]:
            params = {} if path in ["me", "stores"] else {"store_id": seed["store_id"]}
            if path == "sales/summary":
                params |= {"from": "2026-09-01T00:00:00Z", "to": "2026-09-08T00:00:00Z"}
            assert (
                await client.get(
                    "/api/v1/" + path,
                    params=params,
                    headers={"Authorization": "Bearer frontend-service-credential-01"},
                )
            ).status_code == 403
            assert (
                await client.get(
                    "/api/v1/" + path, params=params | {"unknown": "x"}, headers=headers("viewer")
                )
            ).status_code == 422
        duplicate = await client.get(
            "/api/v1/sales",
            params=[("store_id", seed["store_id"]), ("limit", "1"), ("limit", "2")],
            headers=headers("viewer"),
        )
        assert duplicate.status_code == 422
