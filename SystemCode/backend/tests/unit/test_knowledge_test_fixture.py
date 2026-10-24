import pytest


def test_fixture_maps_unique_store_sku_supplier_ids_and_coherent_scenarios():
    from tools.knowledge_test_fixture import fixture_plan

    entities = {
        "stores": [{"fixture_id": "S1"}],
        "suppliers": [{"fixture_id": "P1"}],
        "skus": [
            {
                "fixture_id": "K1",
                "name": "test",
                "store_fixture_ids": ["S1"],
                "supplier_fixture_id": "P1",
            }
        ],
    }
    mapping, scenarios = fixture_plan(entities, "trial01")
    assert mapping["target_database"] == "shopsteward_test"
    assert mapping["seeded"] is False
    assert scenarios[0].store_id == mapping["stores"]["S1"]
    assert scenarios[0].initial_catalog.offers[0].supplier_id == mapping["suppliers"]["P1"]
    assert scenarios[0].initial_catalog.products[0].sku_id == mapping["skus"]["K1"]
    assert fixture_plan(entities, "trial01")[0] == mapping
    assert fixture_plan(entities, "trial02")[0] != mapping


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///test.db",
        "postgresql://localhost/shopsteward",
        "postgresql://remote.example/shopsteward_test",
    ],
)
def test_fixture_rejects_nonlocal_or_nontest_databases_before_connection(url):
    from tools.knowledge_test_fixture import test_database_url

    with pytest.raises(ValueError):
        test_database_url(url)
