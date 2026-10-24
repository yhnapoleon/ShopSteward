from datetime import UTC, datetime
from types import SimpleNamespace

from test_recovery_solver import golden

from app.execution.assisted import arriving_at
from app.planning.recovery.materialize import explanation


def test_an_order_sent_by_hand_counts_in_transit_through_its_delivery_day():
    due = datetime(2026, 10, 22, 7, 8, tzinfo=UTC)  # 15:08 on 22/10 in Shanghai
    later_that_day = datetime(2026, 10, 22, 8, 21, tzinfo=UTC)  # 16:21: the clock moved on
    # Arriving now, the same as past_due says it is not late yet.
    assert arriving_at("assisted", due, later_that_day) == later_that_day
    assert arriving_at("assisted", due, datetime(2026, 10, 21, 7, tzinfo=UTC)) == due
    assert arriving_at("assisted", due, datetime(2026, 10, 22, 16, tzinfo=UTC)) is None  # 23/10
    # The simulator delivers at its ETA: after it, the order is overdue.
    for channel in ("simulator", None):
        assert arriving_at(channel, due, later_that_day) is None
        assert arriving_at(channel, due, datetime(2026, 10, 22, 7, tzinfo=UTC)) == due
    assert arriving_at("assisted", None, later_that_day) is None


def test_the_emergency_line_keeps_the_original_order_only_while_it_is_on_the_way():
    chosen = SimpleNamespace(quantity=30, spend_minor=36000, lost_qty=2)
    recovery = golden()
    assert explanation(chosen, recovery) == (
        "应急补购 30 件，支出 36000 分；七日预测缺货 2 件。原订单保留。"
    )
    # Declined or withdrawn: nothing on the way any more.
    gone = recovery.model_copy(update={"arrivals": []})
    assert explanation(chosen, gone) == "应急补购 30 件，支出 36000 分；七日预测缺货 2 件。"


def test_an_answer_about_a_saved_memory_is_read_both_ways():
    from app.agent_bridge.presentation import memory_failure_claim, memory_success_claim

    for denial in [
        "I didn't save anything this time — the earlier save didn't go through.",
        "Nothing was saved.",
        "这次没有保存成功。",
        "I haven’t saved that preference.",
    ]:
        assert memory_failure_claim(denial) and not memory_success_claim(denial)
    for claim in ["I've saved that: no deliveries on weekends.", "已为你保存。"]:
        assert memory_success_claim(claim) and not memory_failure_claim(claim)
    # Saving one thing and not another is a success that names a limit, not a denial.
    mixed = "I've saved it. I have not saved the cash amount, which is a plan setting."
    assert memory_success_claim(mixed)


async def test_one_request_saves_a_preference_once():
    from unittest.mock import AsyncMock

    from app.agent_bridge.schemas import KnowledgeChange
    from app.agent_bridge.tools import saved_in_run

    content = "I don't take deliveries on weekends."
    earlier = SimpleNamespace(
        result={
            "ok": True,
            "data": {"kind": "USER", "task_type": "", "entries": [{"content": content}]},
        }
    )
    failed = SimpleNamespace(result={"ok": False, "data": {}})
    session = SimpleNamespace(scalars=AsyncMock(return_value=[failed, earlier]))
    run = SimpleNamespace(id="run")

    def change(**fields):
        return KnowledgeChange(expected_version=1, operation="add", **{"content": content} | fields)

    assert await saved_in_run(session, run, change())
    assert await saved_in_run(session, run, change(content="  " + content))
    # Another preference, another scope, or a correction is a change of its own.
    assert not await saved_in_run(session, run, change(content="Call before noon."))
    assert not await saved_in_run(session, run, change(kind="NOTES"))
    replace = KnowledgeChange(
        expected_version=1, operation="replace", entry_id="e", content=content
    )
    assert not await saved_in_run(session, run, replace)
