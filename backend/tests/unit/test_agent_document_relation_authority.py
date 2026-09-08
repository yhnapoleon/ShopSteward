from datetime import UTC, datetime

import pytest


@pytest.mark.parametrize("last_source_current", [True, False])
def test_run_relation_authority_checks_paths_beyond_candidate_limit(last_source_current):
    from app.agent_bridge.document_evidence import (
        all_relation_paths_current,
        current_relation_paths,
    )

    paths, current = [], {}
    for index in range(22):
        version = f"version-{index}"
        edge = {
            "id": f"edge-{index}",
            "subject": "sku",
            "predicate": "requires",
            "object": "permit",
            "confirmed": True,
            "evidence_chunk_ids": [f"chunk-{index}"],
            "version_id": version,
            "generation_id": "generation",
            "metadata_revision": 1,
        }
        paths.append(
            {
                "edge_ids": [edge["id"]],
                "nodes": ["sku", "permit"],
                "edges": [edge],
                "evidence_chunk_ids": edge["evidence_chunk_ids"],
            }
        )
        current[version] = {
            "visible": True,
            "generation_id": "generation",
            "metadata_revision": 1,
        }
    if not last_source_current:
        current["version-21"]["metadata_revision"] = 2
    as_of = datetime(2026, 9, 8, tzinfo=UTC)

    # The candidate-level helper must keep its existing cap. Run validation must
    # neither mistake that cap for stale evidence nor skip a stale final path.
    assert len(current_relation_paths(paths, current, as_of)) == 20
    assert all_relation_paths_current(paths, current, as_of) is last_source_current


def test_no_relation_paths_require_no_relation_authority():
    from app.agent_bridge.document_evidence import all_relation_paths_current

    assert all_relation_paths_current([], {}, datetime(2026, 9, 8, tzinfo=UTC)) is True
