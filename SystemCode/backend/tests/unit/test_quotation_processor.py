"""The quote request's processor: supplier names, business time, rules from chat, one question."""

import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.quotations import processor_tools as quote_tools
from app.quotations import repository as quotes
from app.quotations.schemas import QuoteResult, QuoteRule, QuoteRuleState
from app.work_items import processor as work_processor
from app.work_items import processor_tools as work_tools


class FakeSession:
    """Answers each kind of query in order; there is no database."""

    def __init__(self, scalar=(), scalars=(), execute=(), get=None):
        self.answers = {"scalar": list(scalar), "scalars": list(scalars), "execute": list(execute)}
        self.stored = get

    def next(self, kind, default):
        return self.answers[kind].pop(0) if self.answers[kind] else default

    async def scalar(self, _statement):
        return self.next("scalar", None)

    async def scalars(self, _statement):
        return self.next("scalars", [])

    async def execute(self, _statement):
        return self.next("execute", [])

    async def get(self, *_):
        return self.stored

    @asynccontextmanager
    async def begin(self):
        yield


class FakeDB:
    def __init__(self, session):
        self.current = session

    @asynccontextmanager
    async def session(self):
        yield self.current


def test_every_supplier_id_in_tool_data_gets_its_display_name():
    from app.agent_bridge.presentation import supplier_names_in

    names = {"A": "Anhe Trading", "B": "Baichuan Wholesale"}
    data = {
        "offers": [{"supplier_id": "B", "unit_price_minor": 950}, {"supplier_id": "Z"}],
        "input": {"offer": {"supplier_id": "A", "supplier_name": "Anhe (own name)"}},
        "candidates": [[{"supplier_id": "A", "quantity": 20}]],
    }
    named = supplier_names_in(data, names)
    assert named["offers"][0]["supplier_name"] == "Baichuan Wholesale"
    assert "supplier_name" not in named["offers"][1]
    assert named["input"]["offer"]["supplier_name"] == "Anhe (own name)"
    assert named["candidates"][0][0]["supplier_name"] == "Anhe Trading"
    assert "supplier_name" not in data["offers"][0]
    assert "supplier_name" in work_processor.POLICY and "供应商代码" in work_processor.POLICY


async def test_work_context_gives_business_time_and_names_not_the_server_clock(monkeypatch):
    import app.operations.repository as operations
    import app.reporting.repository as reporting

    simulated = "2026-09-08T09:30:00+00:00"
    wall_clock = "2026-10-21T07:06:00+00:00"

    async def catalog(session, store_id):
        return {
            "store_id": store_id,
            "currency": "CNY",
            "products": [{"sku_id": "ITEM_1", "name": "Fresh milk 1L", "unit": "piece"}],
            "offers": [{"supplier_id": "B", "sku_id": "ITEM_1", "unit_price_minor": 950}],
        }

    async def board(session, store_id, settings):
        return {
            "state": {"state_version": 3, "data_as_of": simulated, "simulation_time": simulated},
            "freshness": {"status": "FRESH", "data_as_of": simulated, "last_sync_at": wall_clock},
            "active_mission_count": 0,
            "active_alert_count": 0,
            "last_check_at": wall_clock,
            "next_check_at": wall_clock,
        }

    async def listing(*args):
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(operations, "get_catalog", catalog)
    monkeypatch.setattr(reporting, "dashboard", board)
    monkeypatch.setattr(work_tools.missions, "list_missions", listing)
    session = FakeSession(execute=[[("B", {})], [("B", "Baichuan Wholesale")]])
    result = await work_tools.execute(
        session,
        Settings(),
        None,
        SimpleNamespace(store_id="SC-01", mission_id=None),
        "get_work_context",
        work_tools.ContextArgs(),
        "call",
    )
    data = result["data"]
    assert data["business_time"] == simulated and data["business_time_local"] == "Tue 08/09 17:30"
    assert "current_time" not in data and "2026-10-21" not in json.dumps(data)
    assert data["catalog"]["offers"][0]["supplier_name"] == "Baichuan Wholesale"


@pytest.mark.parametrize(
    "language,content",
    [
        ("en", "Help organize supplier quotes"),
        ("zh", "帮我整理供应商报价"),
        ("en", "Organize quotes first"),
    ],
)
async def test_asking_to_organize_quotes_before_a_file_gets_one_question(language, content):
    update = await quotes.upload_prompt(FakeSession(), SimpleNamespace(id="w"), content, language)
    assert update["status"] == "WAITING_INPUT"
    assert update["question"] == quotes.text(language, "upload_first")
    assert len(re.findall(r"[.。]", update["question"])) == 1
    with_file = FakeSession(scalar=["file-1"])
    assert await quotes.upload_prompt(with_file, SimpleNamespace(id="w"), content, language) is None


async def test_other_requests_are_not_answered_with_the_upload_question():
    for content in ["哪个供应商报价最便宜？", "Sort by unit price from now on.", "看看库存"]:
        assert (
            await quotes.upload_prompt(FakeSession(), SimpleNamespace(id="w"), content, "en")
            is None
        )


class Model:
    def __init__(self):
        self.calls = []

    async def complete(self, messages, tools, **kwargs):
        self.calls.append(messages)
        raise RuntimeError("provider down")


@pytest.fixture
def harness(monkeypatch):
    """A processor run with storage stubbed out; returns what it published."""
    published = []
    row = SimpleNamespace(id="w", store_id="SC-01", mission_id=None, processing_expires_at=None)
    state = {"messages": [SimpleNamespace(role="user", content="Help organize supplier quotes")]}

    async def fenced(session, settings, lease):
        return row, SimpleNamespace(principal_id="owner")

    async def detail(session, row, settings):
        return SimpleNamespace(messages=state["messages"])

    async def command(session, principal_id, kind, key, content):
        if kind == "work_tool":
            return SimpleNamespace(response=None), False
        snapshot = {"rule_version": state.get("rule_version", 0), "completed_tools": []}
        return SimpleNamespace(id="snap", response=snapshot), True

    async def recall(session, principal_id):
        return "en"

    async def publish(session, service, item_id, update, key, settings, evidence=None):
        published.append(update)
        return update

    import app.agent_bridge.language as language

    monkeypatch.setattr(work_processor, "fenced", fenced)
    monkeypatch.setattr(work_processor.repo, "detail", detail)
    monkeypatch.setattr(work_processor.repo, "publish", publish)
    monkeypatch.setattr(work_processor.missions, "command", command)
    monkeypatch.setattr(language, "recall", recall)
    # One object answers every get: the run's snapshot, and a store with no business clock.
    session = FakeSession(
        get=SimpleNamespace(response={"completed_tools": []}, simulation_time=None)
    )
    return SimpleNamespace(published=published, state=state, db=FakeDB(session))


def lease(input_id):
    return work_processor.Lease("w", 2, "t" * 32, SimpleNamespace(principal_id="p"), input_id)


async def test_a_quote_request_without_a_file_is_one_sentence_and_no_model_run(harness):
    model = Model()
    processor = work_processor.Processor(harness.db, Settings(), model=model)
    await processor.process(lease("m1"))
    assert model.calls == []
    [update] = harness.published
    assert update.status == "WAITING_INPUT" and update.answer is None and update.result is None
    assert update.question == "Upload a quote CSV, or try a sample quote, to start."


async def test_a_run_started_by_an_upload_still_goes_to_the_model(harness):
    model = Model()
    processor = work_processor.Processor(harness.db, Settings(), model=model)
    await processor.process(lease("file:f1"))
    assert len(model.calls) == 1
    assert '"uploaded_file_id": "f1"' in model.calls[0][0]["content"]
    assert harness.published[0].status == "BLOCKED"


class Script:
    def __init__(self, *replies):
        self.replies = list(replies)

    async def complete(self, messages, tools, **kwargs):
        return self.replies.pop(0)


def call(name, args=None):
    function = {"name": name, "arguments": json.dumps(args or {})}
    return {"content": "", "tool_calls": [{"id": name, "type": "function", "function": function}]}


async def test_a_chat_rule_uses_the_run_rule_version_and_later_comparisons_follow_it(
    harness, monkeypatch
):
    harness.state["messages"] = [SimpleNamespace(role="user", content="以后按单件价排序")]
    harness.state["rule_version"] = 3
    seen = {}

    async def execute(session, settings, principal, work, name, args, invocation_id):
        seen[name] = args
        if name == "save_quotation_rule":
            return {"ok": True, "data": {"version": 4, "rule": None}, "references": []}
        table = {"kind": "quotation", "title": "b.csv · 报价整理", "content": "计算完成。"}
        return {"ok": True, "data": {}, "references": [], "work_result": table}

    monkeypatch.setattr(work_processor.tools, "execute", execute)
    monkeypatch.setattr(work_processor, "validate_lease", lambda row, lease, now: None)
    model = Script(
        call("get_work_context"),
        call(
            "save_quotation_rule",
            {
                "result_id": "r1",
                "sort_by": "unit_price",
                "expected_rule_version": 9,
                "confirmation": "以后按单件价排序",
            },
        ),
        call("process_quotation", {"file_id": "f1"}),
        {"content": "已保存并按新规则整理。"},
    )
    await work_processor.Processor(harness.db, Settings(), model=model).process(lease("m2"))
    assert seen["save_quotation_rule"].expected_rule_version == 3
    assert seen["process_quotation"].rule_version == 4
    assert harness.published[0].status == "RESULT_READY"


def quote_result(**changes):
    return QuoteResult(
        id="r1",
        work_id="w",
        file_id="f1",
        filename="sample-quote-B.csv",
        version=1,
        input_sha256="f" * 64,
        sort_by="unit_price",
        rows=[],
        issues=[],
        rule=None,
        corrections=[],
        correction_content="",
        created_at=datetime.now(UTC),
    ).model_copy(update=changes)


def saved(version=1, sort_by="unit_price"):
    return QuoteRuleState(
        version=version,
        rule=QuoteRule(scope_id="scope", version=version, sort_by=sort_by, source={}),
    )


@pytest.fixture
def quote_store(monkeypatch):
    calls = {}

    async def language(session, principal):
        return "en"

    async def result_for_work(session, principal, work, result_id):
        return SimpleNamespace(payload=quote_result().model_dump(mode="json"))

    async def save_rule(session, principal, work, **kwargs):
        calls["save"] = kwargs
        return saved()

    async def process(session, principal, work, body, **kwargs):
        calls["process"] = (body, kwargs)
        return quote_result(id="r2", version=2, rule=kwargs["rule"])

    async def rule_state(session, principal, work, version=None):
        return calls.get("state", saved())

    for name, function in {
        "owner_language": language,
        "result_for_work": result_for_work,
        "save_rule": save_rule,
        "process": process,
        "rule_state": rule_state,
    }.items():
        monkeypatch.setattr(quote_tools.repo, name, function)
    return calls


async def save(session, confirmation, sort_by="unit_price"):
    return await quote_tools.execute(
        session,
        Settings(),
        SimpleNamespace(principal_id="owner"),
        SimpleNamespace(id="w", store_id="SC-01"),
        "save_quotation_rule",
        {
            "result_id": "r1",
            "sort_by": sort_by,
            "expected_rule_version": 0,
            "confirmation": confirmation,
        },
        "call",
    )


async def test_a_rule_asked_for_in_chat_is_saved_and_applied_like_the_form(quote_store):
    request = "Sort by unit price from now on."
    session = FakeSession(scalar=[SimpleNamespace(id="m1", content=request), None])
    result = await save(session, request)
    assert quote_store["save"]["sort_by"] == "unit_price"
    assert quote_store["save"]["source"]["source_message_id"] == "m1"
    body, options = quote_store["process"]
    assert body.file_id == "f1" and body.base_result_id == "r1" and body.sort_by is None
    assert options["rule"].version == 1 and options["rule_loaded"]
    assert result["work_result"]["kind"] == "quotation"
    assert result["work_result"]["title"] == "sample-quote-B.csv · Quote comparison"
    assert {"type": "quotation_rule", "id": "scope:1", "label": "Quote sorting rule"} in result[
        "references"
    ]


async def test_rereading_a_handled_rule_request_after_an_upload_is_not_a_failure(quote_store):
    # The form saved the rule from its own "from now on" line; a run for the next upload
    # reads that line as the latest request. It used to fail and leave the item blocked.
    request = quotes.text("en", "keep_rule")
    session = FakeSession(scalar=[SimpleNamespace(id="m1", content=request), 1])
    result = await save(session, request)
    assert result["ok"] and result["data"]["already_saved"] and result["data"]["version"] == 1
    assert "save" not in quote_store and "process" not in quote_store
    session = FakeSession(scalar=[SimpleNamespace(id="m1", content=request), 1])
    with pytest.raises(AppError) as error:
        await save(session, request, sort_by="source")
    assert error.value.code == "QUOTATION_RULE_REQUEST_HANDLED"


def test_rule_versions_are_pinned_by_the_run_not_asked_of_the_model():
    parameters = work_processor.tool_parameters(quote_tools.SaveRule)
    assert "expected_rule_version" not in parameters["properties"]
    assert set(parameters["required"]) == {"result_id", "sort_by", "confirmation"}
    assert (
        "rule_version"
        not in work_processor.tool_parameters(quote_tools.QuoteProcessArgs)["properties"]
    )


def test_processor_model_follows_the_configured_timeout_within_the_claim():
    settings = Settings(
        agent_model="deepseek-flash", agent_model_timeout_seconds=120, agent_max_output_tokens=4096
    )
    profile = work_processor.model_profile(settings)
    assert (profile.model_id, profile.timeout_s, profile.max_output_tokens) == (
        "deepseek-flash",
        120,
        4096,
    )
    assert work_processor.run_limits(settings) == {"model_timeout": 120, "run_timeout": 240}
    quick = Settings(agent_model_timeout_seconds=30)
    assert work_processor.run_limits(quick) == {"model_timeout": 30, "run_timeout": 90}
