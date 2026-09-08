"""Corpus fixture preparation using the existing business initialization repository."""

import copy
import hashlib
import json
import re
from pathlib import Path


def test_database_url(value):
    from sqlalchemy.engine import make_url

    url = make_url(value)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "shopsteward_test"
        or url.host not in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("dedicated local shopsteward_test database required")
    return url.set(drivername="postgresql+asyncpg")


def fixture_plan(entities, namespace):
    from app.operations.schemas import ScenarioRun

    if not re.fullmatch(r"[a-z0-9-]{1,24}", namespace):
        raise ValueError("invalid test namespace")
    prefix = "knowledge-test-" + namespace + "-"
    mapping = {
        kind: {row["fixture_id"]: prefix + row["fixture_id"] for row in entities[kind]}
        for kind in ("stores", "skus", "suppliers")
    }
    for kind in mapping:
        if len(mapping[kind]) != len(entities[kind]):
            raise ValueError("duplicate fixture identity")
    mapping.update(
        target_database="shopsteward_test",
        seeded=False,
        namespace=namespace,
        default_store_fixture=next(iter(mapping["stores"])),
        entities_sha256=hashlib.sha256(json.dumps(entities, sort_keys=True).encode()).hexdigest(),
    )
    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / "docs/api/services.openapi.json").read_text("utf-8"))
    base = spec["paths"]["/sim/v1/runs"]["post"]["responses"]["201"]["content"]["application/json"][
        "example"
    ]
    scenarios = []
    for fixture_id, store_id in mapping["stores"].items():
        skus = [s for s in entities["skus"] if fixture_id in s["store_fixture_ids"]]
        if not skus:
            raise ValueError("each fixture store needs at least one product")
        seed = copy.deepcopy(base)
        seed.update(store_id=store_id, scenario_run_id=prefix + "run-" + fixture_id)
        for part in ("initial_state", "initial_forecast", "initial_catalog"):
            seed[part]["store_id"] = store_id
        forecast = seed["initial_forecast"]
        forecast.update(
            forecast_id=prefix + "forecast-" + fixture_id,
            sku_id=mapping["skus"][skus[0]["fixture_id"]],
            assumptions=["Synthetic test tenant bootstrap; never inferred from RAG documents."],
        )
        catalog = seed["initial_catalog"]
        offer = copy.deepcopy(catalog["offers"][0])
        catalog["products"], catalog["offers"] = [], []
        stock = copy.deepcopy(seed["initial_state"]["stocks"][0])
        seed["initial_state"]["stocks"] = []
        for sku in skus:
            real_id = mapping["skus"][sku["fixture_id"]]
            catalog["products"].append({"sku_id": real_id, "name": sku["name"], "unit": "piece"})
            catalog["offers"].append(
                offer
                | {
                    "sku_id": real_id,
                    "supplier_id": mapping["suppliers"][sku["supplier_fixture_id"]],
                }
            )
            seed["initial_state"]["stocks"].append(stock | {"sku_id": real_id})
        scenarios.append(ScenarioRun.model_validate(seed))
    return mapping, scenarios


async def seed_fixture(entities, namespace, url):
    from sqlalchemy import text

    from app.db.session import Database
    from app.operations.repository import initialize

    parsed = test_database_url(url)  # Must precede any database connection.
    mapping, scenarios = fixture_plan(entities, namespace)
    db = Database(parsed.render_as_string(hide_password=False))
    try:
        async with db.session() as session, session.begin():
            if await session.scalar(text("SELECT current_database()")) != "shopsteward_test":
                raise ValueError("connected database identity differs")
            for scenario in scenarios:
                await initialize(session, scenario)
        mapping["seeded"] = True
        return mapping
    finally:
        await db.dispose()
