"""Real PostgreSQL intake contract. The adapter is deterministic; no model or supplier."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_missions import body as mission_body
from test_missions import fresh_seed, headers, settings
from test_operations import initialize

from app.core.config import TokenGrant
from app.execution.models import ActionRow
from app.main import create_app
from app.missions.models import MissionRow
from app.work_items.models import WorkItem, WorkMessageRow

pytestmark = pytest.mark.integration
SERVICE = "work-adapter-service-credential-000001"


def service_headers(key=None):
    return {"Authorization": "Bearer " + SERVICE, "Idempotency-Key": key or str(uuid4())}


@asynccontextmanager
async def env(db, **overrides):
    seed = fresh_seed()
    await initialize(db, seed)
    config = settings(db, seed, work_processor_enabled=True, **overrides)
    config.auth_tokens.append(
        TokenGrant(
            token=SERVICE,
            principal_id="adapter",
            kind="service",
            roles=["operator"],
            store_ids=[seed["store_id"]],
        )
    )
    app = create_app(config)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield seed, client, app


async def create(client, seed, content="看看库存，先不采购", key=None):
    r = await client.post(
        "/api/v1/work-items",
        json={"store_id": seed["store_id"], "content": content},
        headers=headers(key=key),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def claim(client, detail, key=None):
    r = await client.post(
        f"/internal/v1/work-items/{detail['item']['id']}/claim",
        json={"expected_version": detail["item"]["version"]},
        headers=service_headers(key),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def publish(client, lease, **changes):
    body = {
        "expected_version": lease["work"]["item"]["version"],
        "processing_token": lease["processing_token"],
        "status": "WAITING_INPUT",
        "question": "活动是哪几天？",
        **changes,
    }
    return await client.post(
        f"/internal/v1/work-items/{lease['work']['item']['id']}/updates",
        json=body,
        headers=service_headers(),
    )


async def test_create_replay_multiturn_and_no_business_write(db):
    async with env(db) as (seed, c, _):
        key = str(uuid4())
        d = await create(c, seed, key=key)
        assert (await create(c, seed, key=key))["item"]["id"] == d["item"]["id"]
        r = await c.post(
            "/api/v1/work-items",
            json={"store_id": seed["store_id"], "content": "different"},
            headers=headers(key=key),
        )
        assert r.status_code == 409
        lease = await claim(c, d)
        asked = await publish(c, lease)
        assert asked.status_code == 200, asked.text
        item = asked.json()["item"]
        key = str(uuid4())
        path = f"/api/v1/work-items/{item['id']}/messages"
        r = await c.post(path, json={"content": "下周六"}, headers=headers(key=key))
        assert r.status_code == 200
        replay = await c.post(path, json={"content": "下周六"}, headers=headers(key=key))
        assert len(replay.json()["messages"]) == 3
        assert replay.json()["item"]["status"] == "RECEIVED"
        lease = await claim(c, replay.json())
        done = await publish(
            c,
            lease,
            status="COMPLETED",
            question=None,
            result={
                "kind": "analysis",
                "title": "活动检查",
                "content": "仍缺对应周期的需求依据，不能据此承诺足够。",
            },
            demonstration=True,
        )
        assert done.status_code == 200, done.text
        async with db.session() as s:
            assert (
                await s.scalar(
                    select(func.count())
                    .select_from(MissionRow)
                    .where(MissionRow.store_id == seed["store_id"])
                )
                == 0
            )
            assert (
                await s.scalar(
                    select(func.count())
                    .select_from(ActionRow)
                    .where(ActionRow.store_id == seed["store_id"])
                )
                == 0
            )
        restored = await c.get(f"/api/v1/work-items/{item['id']}", headers=headers())
        assert restored.json()["item"]["result"]["title"] == "活动检查"
        assert restored.json()["messages"][-1]["demonstration"] is True


async def test_lease_fences_new_input_and_expired_worker(db):
    async with env(db) as (seed, c, _):
        d = await create(c, seed)
        lease = await claim(c, d)
        assert (
            await c.post(
                f"/internal/v1/work-items/{d['item']['id']}/claim",
                json={"expected_version": lease["work"]["item"]["version"]},
                headers=service_headers(),
            )
        ).status_code == 409
        r = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/messages",
            json={"content": "改一下，先只问现金"},
            headers=headers(),
        )
        assert (await publish(c, lease)).status_code == 409
        newer = await claim(c, r.json())
        async with db.session() as s, s.begin():
            row = await s.get(WorkItem, d["item"]["id"])
            row.processing_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert (await publish(c, newer)).status_code == 409
        current = (await c.get(f"/api/v1/work-items/{d['item']['id']}", headers=headers())).json()
        recovered = await claim(c, current)
        assert (await publish(c, recovered)).status_code == 200
        assert (await publish(c, newer)).status_code == 409


async def test_owner_scope_revocation_and_user_cannot_publish(db):
    async with env(db) as (seed, c, app):
        d = await create(c, seed)
        path = f"/api/v1/work-items/{d['item']['id']}"
        assert (await c.get(path, headers=headers("viewer"))).status_code == 404
        assert (await c.get(path, headers=service_headers())).status_code == 403
        assert (
            await c.post(
                f"/internal/v1/work-items/{d['item']['id']}/claim",
                json={"expected_version": 1},
                headers=headers("admin"),
            )
        ).status_code == 403
        lease = await claim(c, d)
        app.state.settings.auth_tokens = [
            g for g in app.state.settings.auth_tokens if g.principal_id != "operator"
        ]
        assert (await publish(c, lease)).status_code == 403


async def test_attach_existing_coalesces_card_without_losing_messages(db):
    async with env(db) as (seed, c, _):
        m = (await c.post("/api/v1/missions", json=mission_body(seed), headers=headers())).json()
        old = (await c.post(f"/api/v1/missions/{m['id']}/work-item", headers=headers())).json()
        assert old["item"]["mission_id"] == m["id"]
        new = await create(c, seed, "上次那个安排少买一点")
        lease = await claim(c, new)
        linked = await publish(c, lease, link_mission_id=m["id"])
        assert linked.status_code == 200, linked.text
        assert linked.json()["item"]["id"] == old["item"]["id"]
        restored = (
            await c.get(f"/api/v1/work-items/{new['item']['id']}", headers=headers())
        ).json()
        assert restored["item"]["id"] == old["item"]["id"]
        assert any(message["content"] == "上次那个安排少买一点" for message in restored["messages"])
        page = (
            await c.get(
                "/api/v1/work-items", params={"store_id": seed["store_id"]}, headers=headers()
            )
        ).json()
        assert len(page["items"]) == 1
        async with db.session() as s:
            assert (
                await s.scalar(
                    select(func.count())
                    .select_from(WorkMessageRow)
                    .where(
                        WorkMessageRow.content == "上次那个安排少买一点",
                        WorkMessageRow.item_id == new["item"]["id"],
                    )
                )
                == 1
            )


async def test_mission_handoff_is_explicit_and_cannot_purchase_or_complete_business(db):
    async with env(db) as (seed, c, _):
        d = await create(c, seed, "帮我跟进备货，至少留500元")
        lease = await claim(c, d)
        proposed = mission_body(seed)
        proposed["policy"]["cash_floor_minor"] = 50000
        r = await publish(
            c,
            lease,
            status="RESULT_READY",
            question=None,
            result={
                "kind": "analysis",
                "title": "备货范围",
                "content": "请核对跟进条件，采购仍逐笔确认。",
            },
            mission_request=proposed,
        )
        assert r.status_code == 200, r.text
        ready = r.json()
        async with db.session() as s:
            assert (
                await s.scalar(
                    select(func.count())
                    .select_from(MissionRow)
                    .where(MissionRow.store_id == seed["store_id"])
                )
                == 0
            )
        path = f"/api/v1/work-items/{d['item']['id']}/mission"
        key = str(uuid4())
        r = await c.post(
            path, json={"expected_version": ready["item"]["version"]}, headers=headers(key=key)
        )
        assert r.status_code == 200, r.text
        again = await c.post(
            path, json={"expected_version": ready["item"]["version"]}, headers=headers(key=key)
        )
        assert again.json()["item"]["mission_id"] == r.json()["item"]["mission_id"]
        assert r.json()["item"]["mission"]["policy"]["cash_floor_minor"] == 50000
        async with db.session() as s:
            assert (
                await s.scalar(
                    select(func.count())
                    .select_from(ActionRow)
                    .where(ActionRow.store_id == seed["store_id"])
                )
                == 0
            )
        sent = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/messages",
            json={"content": "当前怎样了"},
            headers=headers(),
        )
        lease = await claim(c, sent.json())
        assert (
            await publish(
                c,
                lease,
                status="COMPLETED",
                question=None,
                result={"kind": "answer", "title": "回答", "content": "已经回答"},
            )
        ).status_code == 409


async def test_cancel_and_demo_do_not_execute_mission(db):
    async with env(db) as (seed, c, app):
        d = await create(c, seed)
        lease = await claim(c, d)
        stopped = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/control",
            json={"expected_version": lease["work"]["item"]["version"], "operation": "cancel"},
            headers=headers(),
        )
        assert stopped.status_code == 200
        assert (await publish(c, lease)).status_code == 409
        restarted = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/control",
            json={"expected_version": stopped.json()["item"]["version"], "operation": "retry"},
            headers=headers(),
        )
        lease = await claim(c, restarted.json())
        r = await publish(
            c,
            lease,
            status="RESULT_READY",
            question=None,
            demonstration=True,
            result={"kind": "analysis", "title": "模拟委托", "content": "仅验证接口"},
            mission_request=mission_body(seed),
        )
        assert r.status_code == 200
        assert (
            await c.post(
                f"/api/v1/work-items/{d['item']['id']}/mission",
                json={"expected_version": r.json()["item"]["version"]},
                headers=headers(),
            )
        ).status_code == 409
        app.state.settings.app_env = "production"
        sent = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/messages",
            json={"content": "再试一次"},
            headers=headers(),
        )
        lease = await claim(c, sent.json())
        assert (await publish(c, lease, demonstration=True)).status_code == 403


async def test_concurrent_claim_context_and_replay_after_app_recreation(db):
    import asyncio

    async with env(db) as (seed, c, app):
        d = await create(c, seed)
        identifier = d["item"]["id"]
        context = await c.get(
            f"/internal/v1/work-items/{identifier}/context", headers=service_headers()
        )
        assert context.status_code == 200, context.text
        assert context.json()["dashboard"]["state"]["available_cash_minor"] == 100000
        responses = await asyncio.gather(
            *[
                c.post(
                    f"/internal/v1/work-items/{identifier}/claim",
                    json={"expected_version": 1},
                    headers=service_headers(),
                )
                for _ in range(2)
            ]
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        lease = next(r.json() for r in responses if r.status_code == 200)
        payload = {
            "expected_version": lease["work"]["item"]["version"],
            "processing_token": lease["processing_token"],
            "status": "COMPLETED",
            "result": {
                "kind": "answer",
                "title": "查询结果",
                "content": "请核对状态数据时点。",
                "references": [{"type": "store", "id": seed["store_id"], "label": "当前店铺"}],
            },
        }
        key = str(uuid4())
        path = f"/internal/v1/work-items/{identifier}/updates"
        first = await c.post(path, json=payload, headers=service_headers(key))
        assert first.status_code == 200, first.text
        restarted = create_app(app.state.settings)
        async with (
            restarted.router.lifespan_context(restarted),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=restarted), base_url="http://test"
            ) as fresh,
        ):
            replay = await fresh.post(path, json=payload, headers=service_headers(key))
            assert replay.status_code == 200
            assert len(replay.json()["messages"]) == 2
            assert replay.json()["item"]["version"] == first.json()["item"]["version"]
            assert (await fresh.get(f"/api/v1/work-items/{identifier}", headers=headers())).json()[
                "item"
            ]["result"] == first.json()["item"]["result"]


async def test_invalid_evidence_pagination_and_disconnected_processor(db):
    async with env(db) as (seed, c, app):
        a = await create(c, seed, "第一件事")
        b = await create(c, seed, "第二件事")
        page = (
            await c.get(
                "/api/v1/work-items",
                params={"store_id": seed["store_id"], "limit": 1},
                headers=headers(),
            )
        ).json()
        assert page["items"][0]["id"] == b["item"]["id"]
        second = (
            await c.get(
                "/api/v1/work-items",
                params={"store_id": seed["store_id"], "limit": 1, "cursor": page["next_cursor"]},
                headers=headers(),
            )
        ).json()
        assert second["items"][0]["id"] == a["item"]["id"]
        lease = await claim(c, a)
        r = await publish(
            c,
            lease,
            status="COMPLETED",
            question=None,
            result={
                "kind": "answer",
                "title": "错误引用",
                "content": "不得保存",
                "references": [{"type": "store", "id": "another-store", "label": "越界引用"}],
            },
        )
        assert r.status_code == 422
        app.state.settings.work_processor_enabled = False
        r = await c.post(
            f"/internal/v1/work-items/{b['item']['id']}/claim",
            json={"expected_version": 1},
            headers=service_headers(),
        )
        assert r.status_code == 503
        detail = (await c.get(f"/api/v1/work-items/{a['item']['id']}", headers=headers())).json()
        assert detail["item"]["result"] is None
        assert not detail["item"]["processor_available"]


async def test_prior_demo_result_keeps_provenance_after_real_followup_question(db):
    async with env(db) as (seed, c, _):
        d = await create(c, seed)
        lease = await claim(c, d)
        delivered = await publish(
            c,
            lease,
            status="COMPLETED",
            question=None,
            demonstration=True,
            result={"kind": "forecast", "title": "模拟预测", "content": "仅验证接入"},
        )
        assert delivered.status_code == 200
        sent = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/messages",
            json={"content": "补充新的条件"},
            headers=headers(),
        )
        lease = await claim(c, sent.json())
        asked = await publish(c, lease, demonstration=False)
        assert asked.status_code == 200
        assert asked.json()["item"]["demonstration"] is True
        assert asked.json()["item"]["result"]["title"] == "模拟预测"
        assert asked.json()["messages"][-1]["demonstration"] is False


async def test_revoked_owner_does_not_starve_pending_queue(db):
    from app.core.config import TokenGrant

    async with env(db) as (seed, c, app):
        revoked = await create(c, seed)
        other_token = "work-other-owner-credential-0000001"
        app.state.settings.auth_tokens.append(
            TokenGrant(
                token=other_token,
                principal_id="another-owner",
                roles=["viewer"],
                store_ids=[seed["store_id"]],
            )
        )
        other = await c.post(
            "/api/v1/work-items",
            json={"store_id": seed["store_id"], "content": "仍有权限的新事项"},
            headers={"Authorization": "Bearer " + other_token, "Idempotency-Key": str(uuid4())},
        )
        assert other.status_code == 201
        app.state.settings.auth_tokens = [
            grant for grant in app.state.settings.auth_tokens if grant.principal_id != "operator"
        ]
        queue = await c.get(
            "/internal/v1/work-items",
            params={"store_id": seed["store_id"], "limit": 1},
            headers=service_headers(),
        )
        assert queue.status_code == 200
        assert [item["id"] for item in queue.json()["items"]] == [other.json()["item"]["id"]]
        assert revoked["item"]["id"] != other.json()["item"]["id"]


async def test_linked_item_cannot_offer_another_mission(db):
    async with env(db) as (seed, c, _):
        m = (await c.post("/api/v1/missions", json=mission_body(seed), headers=headers())).json()
        d = (await c.post(f"/api/v1/missions/{m['id']}/work-item", headers=headers())).json()
        sent = await c.post(
            f"/api/v1/work-items/{d['item']['id']}/messages",
            json={"content": "看看原安排"},
            headers=headers(),
        )
        lease = await claim(c, sent.json())
        proposed = await publish(
            c,
            lease,
            status="RESULT_READY",
            question=None,
            mission_request=mission_body(seed),
            result={"kind": "answer", "title": "不能重复建立", "content": "原事项已有关联"},
        )
        assert proposed.status_code == 409
        current = (await c.get(f"/api/v1/work-items/{d['item']['id']}", headers=headers())).json()
        assert current["item"]["mission_request"] is None
        assert current["item"]["mission_id"] == m["id"]
