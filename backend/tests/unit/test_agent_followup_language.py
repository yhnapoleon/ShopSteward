from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.core.config import TokenGrant

TOKEN = "operator-token-for-language-tests"


def test_followup_carries_only_the_latest_turns_and_says_so():
    from app.agent_bridge.context_sources import (
        ASSISTANT_HISTORY,
        FOLLOWUP_HISTORY,
        admitted_history,
    )

    rows = []
    for turn in range(1, 21):
        rows.append(
            SimpleNamespace(
                id=f"q{turn}", seq=2 * turn - 1, run_id=f"r{turn}", role="user", content="question"
            )
        )
        rows.append(
            SimpleNamespace(
                id=f"a{turn}", seq=2 * turn, run_id=f"r{turn}", role="assistant", content="answer"
            )
        )
    prior = [f"r{turn}" for turn in range(1, 21)]
    history, admission = admitted_history(
        rows,
        run_id="f",
        conversation_id="c",
        input_through_seq=40,
        prior_run_ids=prior,
        kind="followup",
    )
    assert [m["message_id"] for m in history] == ["q18", "a18", "q19", "a19", "q20", "a20"]
    assert len(history) == FOLLOWUP_HISTORY and admission["kind"] == "followup"
    # A user's own run keeps every question but only the latest answers.
    full, mission = admitted_history(
        rows, run_id="r21", conversation_id="c", input_through_seq=40, prior_run_ids=prior
    )
    answers = [m["message_id"] for m in full if m["role"] == "assistant"]
    assert answers == [f"a{turn}" for turn in range(21 - ASSISTANT_HISTORY, 21)]
    assert len(full) == 20 + ASSISTANT_HISTORY and mission["kind"] == "mission"


def test_english_followup_needs_the_same_evidence_as_chinese():
    from app.agent_bridge.evidence_policy import evidence_policy
    from app.agent_bridge.jobs import FOLLOWUP

    def required(content):
        return evidence_policy(content, documents_enabled=True, forecasts_enabled=True)[
            "required_tools"
        ]

    assert required(FOLLOWUP["en"]) == required(FOLLOWUP["zh"]) == ["get_plan"]


def session_with(statuses):
    return SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: statuses)))


async def test_failed_followup_is_not_redone_and_repeated_failure_pauses_it():
    from app.agent_bridge.triggers import FOLLOWUP_FAILURE_LIMIT, followup_closed

    conversation = SimpleNamespace(
        id="c",
        consumed_trigger=3,
        last_fingerprint="old",
        followup_enabled=True,
        followup_version=4,
    )
    run = SimpleNamespace(
        status="FAILED",
        trigger_watermark=7,
        trigger_fingerprint="new",
        error_code="AGENT_CONTEXT_REQUIRED_OVERFLOW",
    )
    await followup_closed(session_with(["FAILED", "SUCCEEDED", "FAILED"]), conversation, run)
    # The same business state does not start another run; only a later change does.
    assert (conversation.consumed_trigger, conversation.last_fingerprint) == (7, "new")
    assert conversation.followup_enabled is True
    await followup_closed(session_with(["FAILED"] * FOLLOWUP_FAILURE_LIMIT), conversation, run)
    assert conversation.followup_enabled is False and conversation.followup_version == 5


async def test_cancelled_followup_is_handled_without_counting_as_failure():
    from app.agent_bridge.triggers import followup_closed

    conversation = SimpleNamespace(
        id="c",
        consumed_trigger=9,
        last_fingerprint="old",
        followup_enabled=True,
        followup_version=1,
    )
    run = SimpleNamespace(
        status="CANCELLED", trigger_watermark=0, trigger_fingerprint="new", error_code=None
    )
    session = session_with(["FAILED"] * 3)
    await followup_closed(session, conversation, run)
    assert conversation.consumed_trigger == 9 and conversation.last_fingerprint == "new"
    assert conversation.followup_enabled is True
    session.scalars.assert_not_awaited()


async def test_recorded_business_change_makes_an_idle_conversation_due_before_its_interval():
    from app.agent_bridge.triggers import dispatch_followups

    statements = []

    class Session:
        async def scalar(self, statement):
            return datetime.now(UTC)

        async def scalars(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: [])

        def begin(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *error):
            return False

    await dispatch_followups(SimpleNamespace(session=Session), SimpleNamespace(agent_enabled=True))
    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "agent_conversations.next_due <=" in sql
    assert "agent_conversations.active_run_id IS NULL AND (EXISTS" in sql
    assert "agent_triggers.seq > agent_conversations.consumed_trigger" in sql
    assert sql.endswith("FOR NO KEY UPDATE SKIP LOCKED")


async def test_store_change_records_one_trigger_per_active_mission(monkeypatch):
    from app.agent_bridge import triggers

    record = AsyncMock()
    monkeypatch.setattr(triggers, "record_event", record)
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: ["m1", "m2"]))
    )
    await triggers.record_store_change(session, SimpleNamespace(id="s", state_version=12))
    assert [call.args[1:] for call in record.await_args_list] == [
        ("m1", "store-state:s:12", [{"type": "store", "id": "s", "version": "12"}]),
        ("m2", "store-state:s:12", [{"type": "store", "id": "s", "version": "12"}]),
    ]


async def dispatch_with_pending_trigger(
    monkeypatch, plan, action, last_fingerprint=None, received=(), alerts=()
):
    from app.agent_bridge import triggers
    from app.execution.models import ActionRow
    from app.missions.models import MissionRow

    monkeypatch.setattr(triggers, "promote", AsyncMock())
    conversation = SimpleNamespace(
        id="c",
        mission_id="m",
        followup_interval=900,
        active_run_id=None,
        consumed_trigger=3,
        last_fingerprint=last_fingerprint,
        next_seq=10,
    )
    mission = SimpleNamespace(
        id="m", mission_version=2, current_plan_id=plan.id, current_action_id="a", status="ACTIVE"
    )
    added = []

    class Session:
        async def scalar(self, statement):
            # The clock, then the newest pending trigger.
            return datetime.now(UTC) if "clock_timestamp" in str(statement) else 7

        async def scalars(self, statement):
            return SimpleNamespace(all=lambda: [conversation])

        async def execute(self, statement):
            return received if "inbound_items" in str(statement) else alerts

        async def get(self, model, key):
            return {MissionRow: mission, ActionRow: action}.get(model, plan)

        def add(self, row):
            added.append(row)

        async def flush(self):
            pass

        def begin(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *error):
            return False

    await triggers.dispatch_followups(
        SimpleNamespace(session=Session), SimpleNamespace(agent_enabled=True)
    )
    return conversation, added


async def explained(monkeypatch, plan, action, **rows):
    _, [run] = await dispatch_with_pending_trigger(monkeypatch, plan, action, **rows)
    return run.trigger_fingerprint


def pending_plan(identifier, input_hash):
    return SimpleNamespace(id=identifier, input_hash=input_hash, status="PENDING_APPROVAL")


async def test_replan_with_the_same_inputs_consumes_triggers_without_a_run(monkeypatch):
    action = SimpleNamespace(status="EXECUTING")
    last = await explained(monkeypatch, pending_plan("p1", "h"), action)
    # The plan expired and was re-created as a new row with the same inputs.
    conversation, added = await dispatch_with_pending_trigger(
        monkeypatch, pending_plan("p2", "h"), action, last
    )
    assert added == [] and conversation.consumed_trigger == 7


async def test_replan_with_new_inputs_queues_a_followup(monkeypatch):
    action = SimpleNamespace(status="EXECUTING")
    last = await explained(monkeypatch, pending_plan("p1", "h"), action)
    conversation, [run] = await dispatch_with_pending_trigger(
        monkeypatch, pending_plan("p2", "new"), action, last
    )
    assert (run.trigger, run.trigger_watermark) == ("FOLLOWUP", 7)
    assert run.trigger_fingerprint != last and conversation.consumed_trigger == 3


async def test_failed_action_on_the_same_plan_queues_a_followup(monkeypatch):
    executing = SimpleNamespace(status="EXECUTING")
    last = await explained(monkeypatch, pending_plan("p1", "h"), executing)
    _, [run] = await dispatch_with_pending_trigger(
        monkeypatch, pending_plan("p1", "h"), SimpleNamespace(status="FAILED"), last
    )
    assert run.trigger_fingerprint != last


async def test_goods_received_on_the_same_action_queues_a_followup(monkeypatch):
    plan, action = pending_plan("p1", "h"), SimpleNamespace(status="SUCCEEDED")
    last = await explained(monkeypatch, plan, action, received=[("a", "k", 4)])
    _, [run] = await dispatch_with_pending_trigger(
        monkeypatch, plan, action, last, received=[("a", "k", 10)]
    )
    assert run.trigger_fingerprint != last


async def test_new_alert_on_the_same_plan_queues_a_followup(monkeypatch):
    plan, action = pending_plan("p1", "h"), SimpleNamespace(status="SUCCEEDED")
    last = await explained(monkeypatch, plan, action)
    _, [run] = await dispatch_with_pending_trigger(
        monkeypatch, plan, action, last, alerts=[("alert", "WARNING")]
    )
    assert run.trigger_fingerprint != last


def test_interface_language_header_and_prompt_directive():
    from app.agent_bridge.language import directive, requested

    def request(value):
        return SimpleNamespace(headers={"x-ui-language": value} if value is not None else {})

    assert [requested(request(v)) for v in ("en", "EN", "zh", "zh-CN", "fr", "", None)] == [
        "en",
        "en",
        "zh",
        "zh",
        None,
        None,
        None,
    ]
    assert "in English" in directive("en") and directive("en").endswith("\n")
    assert "中文" in directive("zh")
    assert directive(None) == ""


async def test_remembered_language_is_upserted_only_when_it_changes():
    from app.agent_bridge.language import remember

    session = SimpleNamespace(execute=AsyncMock())
    await remember(session, "operator", "en")
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (owner, key) DO UPDATE" in sql
    assert "WHERE agent_receipts.args_hash != excluded.args_hash" in sql


async def test_user_commands_remember_the_interface_language(monkeypatch):
    from app.agent_bridge import language
    from app.api.routing import B0Router

    remembered = AsyncMock()
    monkeypatch.setattr(language, "remember", remembered)

    class Session:
        def begin(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *error):
            return False

    router = B0Router()

    @router.get("/read")
    async def read():
        return {}

    @router.post("/command")
    async def command():
        return {}

    app = FastAPI()
    app.include_router(router)
    app.state.settings = SimpleNamespace(
        auth_tokens=[TokenGrant(token=TOKEN, principal_id="operator", roles=["operator"])]
    )
    app.state.db = SimpleNamespace(session=Session)
    user = {"Authorization": "Bearer " + TOKEN}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Reads, anonymous calls and calls without the header leave the preference alone.
        await client.get("/read", headers={**user, "X-UI-Language": "en"})
        await client.post("/command", headers={"X-UI-Language": "en"})
        await client.post("/command", headers={"Authorization": "Bearer wrong-token-value-xx"})
        await client.post("/command", headers=user)
        assert remembered.await_count == 0
        response = await client.post("/command", headers={**user, "X-UI-Language": "en"})
    assert response.status_code == 200
    assert remembered.await_args.args[1:] == ("operator", "en")


async def test_tool_results_name_every_product_they_mention():
    from app.agent_bridge.tools import product_names, sku_ids

    value = {
        "sku_id": "sku_001",
        "candidates": [{"sku_id": "sku_001"}, {"offer": {"sku_id": "sku_002"}}],
        "money_display": [],
    }
    assert sku_ids(value) == {"sku_001", "sku_002"}
    session = SimpleNamespace(
        execute=AsyncMock(return_value=[("sku_001", {"name": "Fresh milk 1L"}), ("sku_002", {})])
    )
    assert await product_names(session, "s", value) == {"sku_001": "Fresh milk 1L"}
    empty = SimpleNamespace(execute=AsyncMock())
    assert await product_names(empty, "s", {"items": []}) == {}
    empty.execute.assert_not_awaited()
