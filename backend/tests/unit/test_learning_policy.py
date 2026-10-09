from datetime import UTC, datetime, timedelta

import pytest


def test_first_ten_counts_episodes_not_events_and_deduplicates_trigger():
    from app.learning.policy import trigger_candidates

    episodes = [
        dict(
            id=str(i),
            task_family="replenishment",
            occurred_at=(datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=i % 2)).isoformat(),
            eligible=True,
        )
        for i in range(10)
    ]
    assert "first_ten" in [x["kind"] for x in trigger_candidates(episodes, set())]
    assert "first_ten" not in [x["kind"] for x in trigger_candidates(episodes, {"first_ten"})]
    assert not any(x["kind"] == "first_ten" for x in trigger_candidates(episodes[:9], set()))
    assert len(trigger_candidates(episodes + episodes, set())) == len(
        trigger_candidates(episodes, set())
    )


def test_category_needs_two_operating_dates():
    from app.learning.policy import trigger_candidates

    rows = [
        dict(
            id=str(i),
            task_family="replenishment",
            occurred_at="2026-10-01T00:00:00+00:00",
            eligible=True,
        )
        for i in range(3)
    ]
    assert not trigger_candidates(rows, set())
    rows[-1]["occurred_at"] = "2026-10-02T00:00:00+00:00"
    assert trigger_candidates(rows, set())[0]["kind"] == "category"


@pytest.mark.parametrize(
    "status,received,ordered,expected",
    [
        ("SUCCEEDED", 0, 20, "pending"),
        ("SUCCEEDED", 10, 20, "pending"),
        ("UNKNOWN", 0, 20, "unknown"),
        ("SUCCEEDED", 20, 20, "matured"),
    ],
)
def test_outcome_does_not_equate_accepted_to_received(status, received, ordered, expected):
    from app.learning.policy import business_outcome

    assert business_outcome(status, received=received, ordered=ordered) == expected


def test_unknown_and_unexecuted_applications_do_not_count_for_drift():
    from app.learning.policy import assess_drift

    assert not assess_drift([{"stage": "retrieved", "status": "fail"}] * 10)
    assert not assess_drift([{"stage": "executed", "status": "unknown"}] * 10)
    assert assess_drift(
        [{"stage": "executed", "status": "fail"}] * 3
        + [{"stage": "executed", "status": "pass"}] * 7
    )
