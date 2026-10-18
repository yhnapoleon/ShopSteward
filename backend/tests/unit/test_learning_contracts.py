from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def test_scope_is_explicit_and_strict():
    from app.learning.schemas import LearningScope

    with pytest.raises(ValidationError):
        LearningScope(principal_id="u", store_id="s", source_domain="other")
    with pytest.raises(ValidationError):
        LearningScope(principal_id="", store_id="s")


def test_skill_requires_boundaries_and_rejects_extra_fields():
    from app.learning.schemas import SkillSpec

    with pytest.raises(ValidationError):
        SkillSpec(title="bad", task_family="replenishment", procedure=["buy"])
    with pytest.raises(ValidationError):
        SkillSpec(**good_skill(), script="print('buy')")


def good_skill():
    return dict(
        title="Compare delayed supply",
        task_family="supply_delay_recovery",
        summary="Check existing inbound before proposing a new order",
        inputs=["case_id"],
        preconditions=["current_case"],
        exclusions=["unknown_execution"],
        required_tools=["analyze_recovery_case"],
        procedure=["Read inbound", "Compare options"],
        outputs=["comparison"],
        exceptions=["Ask for missing ETA"],
    )


def test_event_availability_cannot_precede_observation():
    from app.learning.schemas import LearningEvent

    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        LearningEvent(
            source_kind="case",
            source_id="c",
            source_version=1,
            event_type="ANALYZED",
            intent_key="case:c",
            task_family="supply_delay_recovery",
            observed_at=now,
            available_at=now.replace(year=now.year - 1),
        )


def test_projection_drops_secrets_and_opaque_text():
    from app.learning.projections import tool_trace

    result = tool_trace(
        "revise_plan",
        {"budget_minor": 120, "api_key": "secret", "text": "token"},
        {"ok": True, "token": "secret", "status": "OPTIONS_READY"},
    )
    assert "secret" not in str(result)
    assert "token" not in str(result)
    assert result["args"]["budget_minor"] == 120
