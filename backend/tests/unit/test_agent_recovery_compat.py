from types import SimpleNamespace


def test_recovery_comparison_preserves_common_candidate_fields():
    from test_planning import example
    from test_recovery_solver import golden

    from app.agent_bridge.outcomes import comparison
    from app.planning.recovery.solver import solve

    document = example()
    recovery = golden()
    solution = solve(recovery)
    document.update(
        plan_kind="recovery_v1",
        selected_candidate_id=solution.recommended_candidate_id,
        candidates=[c.model_dump(mode="json") for c in solution.candidates],
        recovery_intent={
            "case_id": "case",
            "revision": 1,
            "proposal_id": "proposal",
            "selected_candidate_id": solution.recommended_candidate_id,
            "adopted_by": "user",
            "supplier_override": "B",
        },
    )
    document["input_snapshot"]["recovery"] = recovery.model_dump(mode="json")
    document["recommended_candidate_id"] = solution.recommended_candidate_id
    result = comparison(document)
    chosen = next(c for c in result.candidates if c.id == solution.recommended_candidate_id)
    assert chosen.quantity == 20 and chosen.spend_minor == 24000


def test_mission_agents_can_read_cases_but_only_operators_analyze():
    from app.agent_bridge.tools import catalog

    viewer = catalog(SimpleNamespace(roles=["viewer"]))
    operator = catalog(SimpleNamespace(roles=["operator"]))
    assert {"get_recovery_cases", "get_recovery_case"} <= set(viewer)
    assert "analyze_recovery_case" not in viewer
    assert "analyze_recovery_case" in operator
    assert not {"materialize_recovery", "approve", "execute"} & set(operator)
