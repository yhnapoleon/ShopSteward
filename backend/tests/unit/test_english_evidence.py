import pytest

from app.agent_bridge.evidence_policy import evidence_policy
from app.agent_bridge.forecast_evidence import replenishment_requested


@pytest.mark.parametrize(
    "content",
    [
        "Compare a restocking plan for next week",
        "Prepare a purchase plan",
        "Should I restock?",
    ],
)
def test_english_restocking_still_requires_business_and_forecast_evidence(content):
    result = evidence_policy(content, documents_enabled=True, forecasts_enabled=True)
    assert result["required_tools"][:2] == ["get_dashboard", "get_forecast"]
    if "plan" in content:
        assert "get_plan" in result["required_tools"]


@pytest.mark.parametrize("content", ["Don't restock", "Do not replenish", "What is restocking?"])
def test_negated_and_general_english_requests_do_not_force_restocking(content):
    assert not replenishment_requested(content)


def test_english_document_expansion_and_negation():
    assert (
        "read_document_evidence"
        in evidence_policy("Expand the source citation", documents_enabled=True)["required_tools"]
    )
    assert (
        "search_documents"
        not in evidence_policy("Do not search documents", documents_enabled=True)["required_tools"]
    )
    assert (
        "search_documents"
        in evidence_policy("Check supplier terms", documents_enabled=True)["required_tools"]
    )
