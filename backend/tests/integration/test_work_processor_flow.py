"""Real DB/API/Runtime tools with a controlled model, not a provider-quality claim."""

import json

import pytest
from sqlalchemy import func, select
from test_missions import body as mission_body
from test_missions import (
    clean_queue,  # noqa: F401
    headers,
)
from test_work_items import create, env

from app.missions.models import MissionRow
from app.operations.repository import mark_caught_up
from app.work_items.processor import Processor

pytestmark = pytest.mark.integration


def tool(name, args=None):
    return {
        "content": "",
        "tool_calls": [
            {
                "id": name,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {})},
            }
        ],
    }


class ScriptModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.messages = []

    async def complete(self, messages, tools, **kwargs):
        self.messages.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return await reply(messages)
        return reply


async def fresh(db, seed):
    async with db.session() as session, session.begin():
        await mark_caught_up(session, seed["scenario_run_id"], 0)


async def process_item(db, config, model):
    processor = Processor(db, config, model=model)
    lease = await processor.claim_next()
    assert lease is not None
    return await processor.process(lease)


async def test_model_clarifies_and_continues_same_work_without_mission(db):
    async with env(db) as (seed, client, app):
        item = await create(client, seed, "先看看库存和现金")
        model = ScriptModel(
            tool("get_work_context"), tool("clarify", {"question": "要查看哪一个商品？"})
        )
        detail = await process_item(db, app.state.settings, model)
        assert detail.item.status == "WAITING_INPUT"
        await client.post(
            f"/api/v1/work-items/{item['item']['id']}/messages",
            json={"content": "就是sku_001，先只分析"},
            headers=headers(),
        )
        model = ScriptModel(
            tool("get_work_context"), {"content": "已读取当前经营数据，仅分析，不创建委托。"}
        )
        result = await process_item(db, app.state.settings, model)
        assert result.item.id == item["item"]["id"]
        assert result.item.status == "RESULT_READY"
        assert any("先看看库存" in m["content"] for m in model.messages[-1])
        async with db.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(MissionRow)
                    .where(MissionRow.store_id == seed["store_id"])
                )
                == 0
            )


async def test_model_proposes_500_floor_but_only_user_acceptance_creates_mission(db):
    async with env(db) as (seed, client, app):
        await fresh(db, seed)
        source = "请持续跟进sku_001备货，现金至少留500元"
        item = await create(client, seed, source)
        args = {
            "sku_id": "sku_001",
            "supplier_id": "supplier_001",
            "expected_state_version": 1,
            "cash_floor_minor": 50000,
            "candidate_quantities": [0, 20, 40, 80],
            "requested_start": seed["initial_forecast"]["horizon_start"],
            "requested_end": seed["initial_forecast"]["horizon_end"],
            "source_quote": source,
            "objective": "现金至少留500元，持续跟进",
        }
        model = ScriptModel(
            tool("get_work_context"),
            tool("propose_mission", args),
            {"content": "跟进条件已准备，请核对并接受；每笔采购另行确认。"},
        )
        result = await process_item(db, app.state.settings, model)
        assert result.item.status == "RESULT_READY", result
        assert result.item.mission_request.policy.cash_floor_minor == 50000
        assert result.item.mission_id is None
        response = await client.post(
            f"/api/v1/work-items/{item['item']['id']}/mission",
            json={"expected_version": result.item.version},
            headers=headers(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["item"]["mission"]["policy"]["cash_floor_minor"] == 50000


async def test_late_tool_cannot_pause_after_new_user_input(db):
    async with env(db) as (seed, client, app):
        mission = (
            await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        ).json()
        source = "暂停这项备货跟进"
        work = await create(client, seed, source)

        async def late(_):
            await client.post(
                f"/api/v1/work-items/{work['item']['id']}/messages",
                json={"content": "不要暂停了，只查看现状"},
                headers=headers(),
            )
            return tool(
                "control_mission",
                {
                    "mission_id": mission["id"],
                    "operation": "pause",
                    "expected_mission_version": 1,
                    "source_quote": source,
                },
            )

        result = await process_item(
            db, app.state.settings, ScriptModel(tool("get_work_context"), late)
        )
        assert result is None
        current = await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())
        assert current.json()["status"] == "ACTIVE"


async def test_failed_model_retains_completed_tool_and_retry_does_not_pause_twice(db):
    async with env(db) as (seed, client, app):
        mission = (
            await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        ).json()
        source = "暂停这项备货跟进"
        work = await create(client, seed, source)
        args = {
            "mission_id": mission["id"],
            "operation": "pause",
            "expected_mission_version": 1,
            "source_quote": source,
        }
        first = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("control_mission", args),
                RuntimeError("provider unavailable"),
            ),
        )
        assert first.item.status == "BLOCKED"
        await client.post(
            f"/api/v1/work-items/{work['item']['id']}/control",
            json={"expected_version": first.item.version, "operation": "retry"},
            headers=headers(),
        )
        args["expected_mission_version"] = 2
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("control_mission", args),
                {"content": "后续备货跟进已暂停，已发订单不受影响。"},
            ),
        )
        assert result.item.status == "RESULT_READY", result
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["status"] == "PAUSED" and current["mission_version"] == 2


async def test_model_failure_keeps_previous_result(db):
    async with env(db) as (seed, client, app):
        work = await create(client, seed)
        first = await process_item(
            db,
            app.state.settings,
            ScriptModel(tool("get_work_context"), {"content": "仅分析完成。"}),
        )
        result_id = first.item.result.provenance.result_id
        await client.post(
            f"/api/v1/work-items/{work['item']['id']}/messages",
            json={"content": "再解释一下"},
            headers=headers(),
        )
        result = await process_item(
            db, app.state.settings, ScriptModel(RuntimeError("provider failure"))
        )
        assert result.item.status == "BLOCKED"
        assert result.item.result.provenance.result_id == result_id


async def test_revoked_users_do_not_starve_valid_work(db):
    from uuid import uuid4

    from app.work_items.models import WorkItem

    async with env(db) as (seed, client, app):
        async with db.session() as session, session.begin():
            for _ in range(35):
                session.add(
                    WorkItem(
                        id=str(uuid4()),
                        store_id=seed["store_id"],
                        principal_id="revoked-user",
                        title="unowned old work",
                    )
                )
        work = await create(client, seed, "查看库存")
        processor = Processor(db, app.state.settings)
        lease = await processor.claim_next()
        assert lease.item_id == work["item"]["id"]


async def test_existing_mission_work_is_reused_before_mutation(db):
    async with env(db) as (seed, client, app):
        mission = (
            await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        ).json()
        original = (
            await client.post(f"/api/v1/missions/{mission['id']}/work-item", headers=headers())
        ).json()
        # Existing work is already settled, so the new incoming work is claimed first.
        from app.work_items.models import WorkItem

        async with db.session() as session, session.begin():
            row = await session.get(WorkItem, original["item"]["id"])
            row.status = "RESULT_READY"
        source = "暂停这项备货跟进"
        new = await create(client, seed, source)
        args = {
            "mission_id": mission["id"],
            "operation": "pause",
            "expected_mission_version": 1,
            "source_quote": source,
        }
        first = await process_item(
            db,
            app.state.settings,
            ScriptModel(tool("get_work_context"), tool("control_mission", args)),
        )
        assert first is None
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["status"] == "ACTIVE"
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("control_mission", args),
                {"content": "已暂停后续跟进。"},
            ),
        )
        assert result.item.id == original["item"]["id"]
        assert result.item.mission.mission_version == 2
        alias = (
            await client.get(f"/api/v1/work-items/{new['item']['id']}", headers=headers())
        ).json()
        assert alias["item"]["id"] == original["item"]["id"]


async def test_real_inventory_answer_has_amount_unit_and_actual_time(db):
    async with env(db) as (seed, client, app):
        await fresh(db, seed)
        work = await create(client, seed, "查看真实库存、现金和在途，注明时点")

        async def answer(messages):
            data = json.loads(
                next(m["content"] for m in reversed(messages) if m["role"] == "tool")
            )["data"]
            state = data["dashboard"]["state"]
            stock = state["stocks"][0]
            money = next(
                f["yuan"]
                for f in data["money_display"]
                if f["field"].endswith("available_cash_minor")
            )
            return {
                "content": (
                    f"截至{state['data_as_of']}，可用现金{money}元；"
                    f"现货{stock['on_hand']}件，在途{stock['in_transit']}件。经营来源为模拟环境。"
                )
            }

        result = await process_item(
            db, app.state.settings, ScriptModel(tool("get_work_context"), answer)
        )
        assert result.item.id == work["item"]["id"]
        assert "1000.00元" in result.item.result.content
        assert "20件" in result.item.result.content and "在途0件" in result.item.result.content
        assert seed["initial_state"]["data_as_of"][:19] in result.item.result.content
        assert result.item.result.references[0].type == "store"
        assert result.item.result.provenance.state_version == 1
        assert result.item.result.provenance.data_as_of is not None
        assert not any("工具已完成（回执数据）" in m.content for m in result.messages)


async def test_readonly_comparison_then_explicit_revision_creates_new_pending_plan(db):
    from app.missions.models import PlanRow
    from app.planning.jobs import make_handlers as planning
    from app.scheduling.runner import Runner

    async with env(db) as (seed, client, app):
        await fresh(db, seed)
        mission = (
            await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        ).json()
        await Runner(db, app.state.settings, handlers=planning(app.state.settings)).run_once()
        async with db.session() as session:
            row = await session.get(MissionRow, mission["id"])
            original = await session.get(PlanRow, row.current_plan_id)
            original_id, original_document = original.id, dict(original.document)
        work = await create(client, seed, "只比较最多采购20件，不修改方案")
        args = {"mission_id": mission["id"], "plan_id": original_id, "max_purchase_qty": 20}
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("evaluate_plan", args),
                {"content": "已完成只读比较，原方案未修改。"},
            ),
        )
        assert result.item.status == "RESULT_READY"
        async with db.session() as session:
            row = await session.get(MissionRow, mission["id"])
            assert row.current_plan_id == original_id and row.mission_version == 1
        source = "把当前方案修改成最多采购20件"
        await client.post(
            f"/api/v1/work-items/{work['item']['id']}/messages",
            json={"content": source},
            headers=headers(),
        )
        revised_args = {**args, "expected_mission_version": 1, "source_quote": source}
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("revise_plan", revised_args),
                {"content": "新待确认方案已生成，采购仍需确认。"},
            ),
        )
        assert result.item.status == "RESULT_READY", result
        async with db.session() as session:
            row = await session.get(MissionRow, mission["id"])
            old = await session.get(PlanRow, original_id)
            new = await session.get(PlanRow, row.current_plan_id)
            assert old.status == "SUPERSEDED" and old.document == original_document
            assert new.status == "PENDING_APPROVAL" and new.id != old.id
            assert new.document["proposed_purchase"]["quantity"] == 20
            assert row.policy["cash_floor_minor"] == 30000


async def test_stop_analysis_leaves_mission_and_order_cancellation_is_not_a_tool(db):
    from app.work_items.processor_tools import definitions

    assert not {"cancel_order", "cancel_action", "approve_plan"} & definitions().keys()
    async with env(db) as (seed, client, app):
        mission = (
            await client.post("/api/v1/missions", json=mission_body(seed), headers=headers())
        ).json()
        source = "停止这次分析"
        work = await create(client, seed, source)
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("stop_analysis", {"source_quote": source}),
                {"content": "本次分析已停止。"},
            ),
        )
        assert result.item.status == "CANCELLED"
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["status"] == "ACTIVE" and current["mission_version"] == 1
        # Even a misbehaving model cannot invent an order cancellation capability.
        await client.post(
            f"/api/v1/work-items/{work['item']['id']}/messages",
            json={"content": "撤回已发采购订单"},
            headers=headers(),
        )
        result = await process_item(
            db,
            app.state.settings,
            ScriptModel(tool("get_work_context"), tool("cancel_order", {"id": "invented"})),
        )
        assert result.item.status == "BLOCKED"
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["status"] == "ACTIVE"


async def test_runtime_quotation_a_saves_rule_and_b_uses_own_rows(db):
    from test_quotations import HEADER, upload

    async with env(db) as (seed, client, app):
        source = "整理此报价；以后每次都按单件价排序"
        a = (await create(client, seed, source))["item"]
        file_a = await upload(client, a, HEADER + "A,120,CNY,箱,12,2,箱,甲")

        # A's rule save must use the actual result from the preceding tool.
        async def save_rule(messages):
            result = json.loads(
                next(m["content"] for m in reversed(messages) if m["role"] == "tool")
            )["data"]
            return tool(
                "save_quotation_rule",
                {
                    "result_id": result["id"],
                    "sort_by": "unit_price",
                    "expected_rule_version": 0,
                    "confirmation": "以后每次都按单件价排序",
                },
            )

        model = ScriptModel(
            tool("get_work_context"),
            tool("process_quotation", {"file_id": file_a["id"], "sort_by": "unit_price"}),
            save_rule,
            {"content": "报价已整理，长期排序规则已保存。"},
        )
        result_a = await process_item(db, app.state.settings, model)
        assert result_a.item.status == "RESULT_READY", result_a
        assert result_a.item.result.kind == "quotation"
        b = (await create(client, seed, "整理另一份报价，沿用已经保存的规则"))["item"]
        file_b = await upload(
            client, b, HEADER + "果汁,240,CNY,箱,10,2,箱,乙\n饮料,180,CNY,箱,15,3,箱,乙"
        )
        result_b = await process_item(
            db,
            app.state.settings,
            ScriptModel(
                tool("get_work_context"),
                tool("process_quotation", {"file_id": file_b["id"]}),
                {"content": "已按已保存规则整理新报价，饮料12元/件。"},
            ),
        )
        assert result_b.item.status == "RESULT_READY", result_b
        history = (
            await client.get(f"/api/v1/work-items/{b['id']}/quotation-results", headers=headers())
        ).json()["items"]
        assert len(history) == 1
        quote = history[0]
        assert quote["rule"]["version"] == 1
        assert quote["rows"][0]["unit_price"] == "12" and quote["rows"][0]["moq_pieces"] == "45"
        assert quote["rows"][1]["unit_price"] == "24"
        assert quote["corrections"] == []
        assert quote["file_id"] == file_b["id"] and quote["rule"]["source"]["work_id"] == a["id"]
        provenance = result_b.item.result.provenance
        assert provenance.state_version is None and provenance.data_as_of is None
        assert provenance.source_type == "quotation"
        versions = provenance.reference_versions
        assert versions["quotation_file:" + file_b["id"]] == "sha256:" + file_b["sha256"]
        assert versions["quotation_result:" + quote["id"]] == str(quote["version"])
        rule_id = quote["rule"]["scope_id"] + ":1"
        assert versions["quotation_rule:" + rule_id] == "1"
        export_path = f"/api/v1/work-items/{b['id']}/results/{provenance.result_id}"
        exported = await client.get(export_path, headers=headers())
        assert exported.status_code == 200 and exported.json()["stale_reasons"] == []
        from app.operations.models import Store

        async with db.session() as session, session.begin():
            store = await session.get(Store, seed["store_id"])
            store.state_version += 1
        exported = await client.get(export_path, headers=headers())
        assert exported.status_code == 200 and exported.json()["stale_reasons"] == []
        assert exported.json()["result"]["provenance"]["reference_versions"] == versions


@pytest.mark.parametrize(
    "claim",
    [
        "已取消订单。",
        "已采购并付款。",
        "已暂停备货跟进。",
        "新待确认方案已生成。",
        "已保存长期报价规则。",
    ],
)
async def test_model_cannot_claim_action_success_without_receipt(db, claim):
    async with env(db) as (seed, client, app):
        await create(client, seed, "先查看现状，不执行操作")
        result = await process_item(
            db, app.state.settings, ScriptModel(tool("get_work_context"), {"content": claim})
        )
        assert result.item.status == "BLOCKED"
        assert result.item.result is None
        assert not any(m.content == claim for m in result.messages)
