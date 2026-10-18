def test_authenticated_case_routes_and_recovery_plan_are_in_runtime_contract():
    from app.core.config import Settings
    from app.main import create_app

    spec = create_app(Settings(_env_file=None)).openapi()
    assert "/api/v1/operations-cases" in spec["paths"]
    assert "/api/v1/operations-cases/{case_id}/analyze" in spec["paths"]
    assert "RecoveryPlan" in spec["components"]["schemas"]
