"""K0 C/D comparison: fixed PostgreSQL joins vs bounded recursive SQL.

Both use the exact same fixture facts, scope, query plan and path conditions.
Only connection-local temporary tables in shopsteward_test are written. This is
not an NL query planner, rule engine, graph database or end-to-end RAG benchmark.
"""

import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402


def doc_allowed(doc, principal, date, historical=False):
    return (
        doc["store_id"] == principal["store_id"]
        and principal["role"] in doc["allowed_roles"]
        and doc["status"] == "published"
        and (historical or doc["valid_from"] <= date < doc["valid_until"])
    )


def eligible_edges(edges, documents, principal, case):
    plan = case["query_plan"]
    context = plan["qualifier_context"]
    out = []
    for edge in edges:
        if (
            edge["store_id"] != principal["store_id"]
            or edge["assertion_status"] != "verified"
            or not edge["valid_from"] <= case["as_of"] < edge["valid_until"]
            or edge["predicate"] not in plan["allowed_predicates"]
        ):
            continue
        source = edge.get("source_version_id")
        if source and not doc_allowed(documents[source], principal, case["as_of"]):
            continue
        hidden = False
        for side in ("subject", "object"):
            if edge[f"{side}_type"] == "DocumentVersion":
                # Lineage may expose an old version ID, never authorize its body.
                historical = (
                    side == "object"
                    and edge["predicate"] == "SUPERSEDES"
                    and context.get("allow_historical_target_metadata", False)
                )
                if not doc_allowed(
                    documents[edge[f"{side}_id"]], principal, case["as_of"], historical
                ):
                    hidden = True
        if hidden:
            continue
        qualifiers = edge["qualifiers"]
        if any(
            key in context and key in qualifiers and context[key] != qualifiers[key]
            for key in ("mission_id", "mission_status", "action_status", "use")
        ):
            continue
        if qualifiers.get("allowed_roles") and principal["role"] not in qualifiers["allowed_roles"]:
            continue
        if edge["predicate"] == "POTENTIAL_SUBSTITUTE_FOR":
            # Unknown prerequisite is not approval. Reverse association is never
            # used to reverse a substitution claim.
            if any(
                key in qualifiers and context.get(key) != qualifiers[key]
                for key in ("mission_id", "use")
            ):
                continue
            if (
                qualifiers.get("customer_consent_required")
                and context.get("customer_consent") is not True
            ):
                continue
            if (
                qualifiers.get("nut_label_required")
                and context.get("nut_label_present") is not True
            ):
                continue
            if (
                qualifiers.get("nut_allergy_claim_allowed") is False
                and context.get("nut_allergy_claim") is not False
            ):
                continue
        directions = ["forward"]
        if plan["direction"] == "both" and edge["predicate"] != "POTENTIAL_SUBSTITUTE_FOR":
            directions.append("reverse")
        for direction in directions:
            start, end = ("subject", "object") if direction == "forward" else ("object", "subject")
            out.append(
                {
                    "edge_id": edge["edge_id"],
                    "start_id": edge[f"{start}_id"],
                    "end_id": edge[f"{end}_id"],
                    "end_type": edge[f"{end}_type"],
                    "direction": direction,
                }
            )
    return out


def fixed_join_sql(depth):
    selections = []
    for size in range(1, depth + 1):
        names = [f"e{i}" for i in range(1, size + 1)]

        def arrays(field, names=names):
            return "ARRAY[" + ",".join(n + "." + field for n in names) + "]"

        clauses = ["e1.start_id = ANY(:seeds)"]
        joins = "k0_edges e1"
        for i in range(2, size + 1):
            joins += f" JOIN k0_edges e{i} ON e{i - 1}.end_id = e{i}.start_id"
        for i in range(1, size + 1):
            prior = ["e1.start_id"] + [f"e{j}.end_id" for j in range(1, i)]
            clauses.append(f"e{i}.end_id <> ALL(ARRAY[" + ",".join(prior) + "])")
        selections.append(
            "SELECT "
            + arrays("edge_id")
            + " AS edges, "
            + arrays("direction")
            + " AS directions, ARRAY[e1.start_id] || "
            + arrays("end_id")
            + f" AS nodes, e{size}.end_type AS end_type "
            + "FROM "
            + joins
            + " WHERE "
            + " AND ".join(clauses)
        )
    return " UNION ALL ".join(selections)


RECURSIVE = """
WITH RECURSIVE paths AS (
 SELECT ARRAY[edge_id] AS edges, ARRAY[direction] AS directions,
        ARRAY[start_id, end_id] AS nodes, end_id, end_type
 FROM k0_edges WHERE start_id = ANY(:seeds) AND start_id <> end_id
 UNION ALL
 SELECT p.edges || e.edge_id, p.directions || e.direction,
        p.nodes || e.end_id, e.end_id, e.end_type
 FROM paths p JOIN k0_edges e ON p.end_id = e.start_id
 WHERE cardinality(p.edges) < :depth AND NOT e.end_id = ANY(p.nodes)
)
SELECT edges, directions, nodes, end_type FROM paths
"""


def constrain_paths(rows, plan, edges):
    output = []
    context = plan["qualifier_context"]
    node_types = {
        edge[f"{side}_id"]: edge[f"{side}_type"]
        for edge in edges.values()
        for side in ("subject", "object")
    }
    for row in rows:
        if row["end_type"] not in plan["target_types"]:
            continue
        if plan["target_entity_ids"] and row["nodes"][-1] not in plan["target_entity_ids"]:
            continue
        facts = [edges[eid] for eid in row["edges"]]
        sku_nodes = {node for node in row["nodes"] if node_types[node] == "SKU"}
        if context.get("sku_id") and sku_nodes and sku_nodes != {context["sku_id"]}:
            continue
        if context.get("apply_notice_sku_scope"):
            if any(
                (q.get("only_skus") and not sku_nodes <= set(q["only_skus"]))
                or sku_nodes & set(q.get("excluded_skus", []))
                for q in [e["qualifiers"] for e in facts]
            ):
                continue
        substitutions = [e for e in facts if e["predicate"] == "POTENTIAL_SUBSTITUTE_FOR"]
        if len(substitutions) > 1 and any(
            e["qualifiers"].get("transitive") is False for e in substitutions
        ):
            continue
        output.append(
            {
                "path": [
                    {"edge_id": eid, "direction": direction}
                    for eid, direction in zip(row["edges"], row["directions"], strict=True)
                ],
                "nodes": row["nodes"],
                "qualifiers": [e["qualifiers"] for e in facts],
                "evidence_versions": sorted(
                    {e["source_version_id"] for e in facts if e.get("source_version_id")}
                ),
            }
        )
    return sorted(output, key=lambda row: json.dumps(row["path"], sort_keys=True))


async def main():
    corpus = ROOT / "docs/evaluation/knowledge"

    def read(name):
        return json.loads((corpus / name).read_text("utf-8"))

    documents = {d["version_id"]: d for d in read("corpus-manifest.json")["documents"]}
    fixture = read("entities-fixture.json")
    edges = read("relations.json")["edges"]
    edge_map = {edge["edge_id"]: edge for edge in edges}
    cases = [
        json.loads(line)
        for line in (corpus / "relation-cases.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    settings = Settings(_env_file=ROOT / "backend/.env")
    url = make_url(settings.database_url.get_secret_value()).set(database="shopsteward_test")
    assert url.database == "shopsteward_test"
    engine = create_async_engine(url, connect_args={"command_timeout": 10})
    results = []
    try:
        async with engine.begin() as conn:
            pg = await conn.scalar(text("SELECT version()"))
            await conn.execute(
                text(
                    "CREATE TEMP TABLE k0_edges (edge_id text, start_id text, end_id text, "
                    "end_type text, direction text) ON COMMIT DROP"
                )
            )
            for case in cases:
                plan = case["query_plan"]
                assert 1 <= plan["max_depth"] <= 3
                allowed = eligible_edges(
                    edges, documents, fixture["principals"][case["store_fixture"]], case
                )
                await conn.execute(text("TRUNCATE pg_temp.k0_edges"))
                if allowed:
                    await conn.execute(
                        text(
                            "INSERT INTO pg_temp.k0_edges VALUES "
                            "(:edge_id,:start_id,:end_id,:end_type,:direction)"
                        ),
                        allowed,
                    )
                comparison = {}
                for label, sql in (
                    ("C_fixed_joins", fixed_join_sql(plan["max_depth"])),
                    ("D_recursive", RECURSIVE),
                ):
                    started = time.perf_counter()
                    rows = (
                        (
                            await conn.execute(
                                text(sql),
                                {"seeds": plan["seed_entity_ids"], "depth": plan["max_depth"]},
                            )
                        )
                        .mappings()
                        .all()
                    )
                    paths = constrain_paths(rows, plan, edge_map)
                    comparison[label] = {
                        "paths": paths,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                actual = [p["path"] for p in comparison["C_fixed_joins"]["paths"]]
                expected = sorted(
                    case["expected_paths"], key=lambda row: json.dumps(row, sort_keys=True)
                )
                same = comparison["C_fixed_joins"]["paths"] == comparison["D_recursive"]["paths"]
                assert same, case["id"]
                assert actual == expected, (case["id"], actual, expected)
                results.append(
                    {
                        "id": case["id"],
                        "split": case["split"],
                        "group": case["group"],
                        "same_paths": same,
                        "expected_paths_match": actual == expected,
                        "comparison": comparison,
                        "completeness": "open_world_not_guaranteed",
                        "answer_assertions": (
                            "not_scored; no text generation or parsing in this experiment"
                        ),
                    }
                )
    finally:
        await engine.dispose()
    result = {
        "ran_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "postgresql": pg,
        "scope": (
            "connection-local temporary table in shopsteward_test; no business tables modified"
        ),
        "profile": (
            "assistant-authored explicit query plans, same facts/filters/conditions; "
            "fixed joins vs recursive SQL"
        ),
        "limits": [
            "Manual graph facts may refer to scanned evidence not yet OCR-readable.",
            "No natural-language planning, full answer correctness, Neo4j, or embedding measured.",
            "12 fixtures do not establish performance/scalability superiority.",
        ],
        "input_hashes": {
            name: hashlib.sha256((corpus / name).read_bytes()).hexdigest()
            for name in [
                "relations.json",
                "relation-cases.jsonl",
                "entities-fixture.json",
                "corpus-manifest.json",
            ]
        },
        "cases": results,
        "case_count": len(results),
        "splits": {s: sum(c["split"] == s for c in results) for s in ["dev", "test"]},
        "decision": (
            "No path-correctness gain from recursive traversal over equivalent fixed joins "
            "in these fixtures; keep PG relations."
        ),
    }
    (ROOT / "docs/api/knowledge-k0-relations-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(json.dumps({"status": "passed", "cases": len(results), "same_paths": True}))


if __name__ == "__main__":
    asyncio.run(main())
