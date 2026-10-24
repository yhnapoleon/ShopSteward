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


def test_a_case_read_by_the_agent_keeps_options_offers_and_findings_only():
    import json

    from app.agent_bridge.tools import case_for_agent, case_summary

    daily = [
        {"settlement_at": f"2026-10-2{i}T08:31:00Z", "demand_qty": 10, "lost_qty": i // 2}
        for i in range(7)
    ]
    claims = [{"kind": "source_fact", "statement": "x" * 900, "support": ["id"]}] * 18 + [
        {"kind": "interpretation", "statement": "B_30 covers the most demand.", "support": []}
    ]
    detail = {
        "id": "case",
        "sku_id": "sku_001",
        "status": "OPEN",
        "objective": "cover the gap",
        "budget_minor": 100000,
        "proposal": {
            "id": "p",
            "recommended_candidate_id": "B_30",
            "candidate_set_hash": "h" * 64,
            "candidates": [{"id": "B_30", "quantity": 30, "spend_minor": 28500, "daily": daily}],
        },
        "sourcing": {
            "status": "complete",
            "budget": {"entries": {str(i): {"kind": "tool"} for i in range(80)}},
            "reviews": [
                {
                    "supplier_id": "B",
                    "name": "Huaxin Dairy",
                    "status": "accepted",
                    "attempts": [{"opened": ["B-quote"] * 20}],
                    "card": {
                        "status": "offer",
                        "offer": {"unit_price_minor": 950, "lead_time_days": 1},
                        "citations": [{"quote": "q" * 400}] * 6,
                    },
                }
            ],
        },
        "expert_analysis": {
            "status": "partial",
            "merged": {"claims": claims, "missing": [{"item": "no guarantee"}], "conflicts": []},
            "subtasks": [{"claims": claims}],
            "call_records": [{"request_hash": "r" * 64}] * 20,
        },
        "evidence": [{"id": "B", "kind": "supplier_offer", "status": "verified_source"}],
    }
    value = case_for_agent(detail)
    assert len(json.dumps(value)) < len(json.dumps(detail)) / 5
    candidate = value["proposal"]["candidates"][0]
    assert "daily" not in candidate and candidate["first_short_at"] == "2026-10-22T08:31:00Z"
    assert value["sourcing"]["suppliers"][0]["offer"]["unit_price_minor"] == 950
    assert value["sourcing"]["suppliers"][0]["name"] == "Huaxin Dairy"
    assert value["expert_analysis"]["findings"] == ["B_30 covers the most demand."]
    assert {"budget_minor", "objective", "status"} <= set(value)
    summary = case_summary(detail)
    assert summary["recommended_candidate_id"] == "B_30" and "proposal" not in summary


def test_an_answer_citing_a_case_still_completes_its_job():
    from app.agent_bridge.jobs import scheduler_references
    from app.api.schemas import JobResult

    references = scheduler_references(
        [
            {"type": "case", "id": "case-1", "version": "2"},
            {"type": "forecast", "id": "f", "version": "m1"},
            {"type": "document", "id": "d", "version_id": "v"},
            {"type": "plan", "id": "p", "version": "3"},
        ]
    )
    JobResult.model_validate({"summary": "answer", "references": references})
    assert references[0] == {"type": "artifact", "id": "case-1", "version": "2"}
    assert references[2] == {"type": "artifact", "id": "d", "version": "v"}
    assert references[3]["type"] == "plan"
