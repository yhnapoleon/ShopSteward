import pytest

REQUIRED = ("corpus_200", "real_http", "restore", "versioning", "agent_tools", "build")


@pytest.mark.parametrize("key", REQUIRED)
@pytest.mark.parametrize("status", ["not_run", "failed", "skipped", True, None, "PASSED"])
def test_every_required_check_must_explicitly_pass(key, status):
    from shopsteward_knowledge.readiness import ready_for_cloud_pilot

    checks = dict.fromkeys(REQUIRED, "passed")
    checks[key] = status
    assert ready_for_cloud_pilot(checks) is False


@pytest.mark.parametrize("missing", REQUIRED)
def test_missing_evidence_cannot_pass(missing):
    from shopsteward_knowledge.readiness import ready_for_cloud_pilot

    checks = dict.fromkeys(REQUIRED, "passed")
    del checks[missing]
    assert ready_for_cloud_pilot(checks) is False


def test_local_pilot_does_not_claim_cloud_quality():
    from shopsteward_knowledge.readiness import ready_for_cloud_pilot

    checks = dict.fromkeys(REQUIRED, "passed")
    checks.update(cloud_model_quality="not_run", cloud_latency="not_run", cloud_cost="not_run")
    assert ready_for_cloud_pilot(checks) is True
    assert checks["cloud_model_quality"] == "not_run"
