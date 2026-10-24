"""Offline evidence scoring only. This module never sends queries to a retrieval service."""

from .validate import read_jsonl


def export_queries(cases):
    """Stable dev-only request projection; never copy arbitrary case/gold dictionaries."""
    requests, seen = [], set()
    constraint_types = {
        "store_fixture": str,
        "as_of": str,
        "target_sku": str,
        "proof_available": bool,
        "graph_complete": bool,
    }
    for case in cases:
        if case.get("split") != "dev":
            continue
        request = {
            key: case[key] for key in ("case_id", "split", "query", "store_fixture", "as_of")
        }
        if any(not isinstance(value, str) or not value for value in request.values()):
            raise ValueError("dev request fields must be nonempty strings")
        if request["case_id"] in seen:
            raise ValueError("duplicate dev case_id")
        seen.add(request["case_id"])
        entries = case.get("entry_entities", [])
        if not isinstance(entries, list) or any(not isinstance(v, str) for v in entries):
            raise ValueError("entry_entities must contain identifiers only")
        request["entry_entities"] = list(entries)
        constraints = case.get("query_constraints", {})
        if not isinstance(constraints, dict):
            raise ValueError("query_constraints must be an object")
        projected = {}
        for key, value_type in constraint_types.items():
            if key in constraints:
                if type(constraints[key]) is not value_type:
                    raise ValueError("query constraint must have its declared scalar type")
                projected[key] = constraints[key]
        request["query_constraints"] = projected
        requests.append(request)
    return sorted(requests, key=lambda row: row["case_id"])


def required_evidence_recall(required: list[set[str]], retrieved: set[str]) -> float | None:
    if not required:
        return None
    return sum(bool(set(choices) & retrieved) for choices in required) / len(required)


def evaluate(result_file, case_file):
    cases = read_jsonl(case_file)
    rows = read_jsonl(result_file)
    if not rows:
        raise ValueError("actual retrieval results required before scoring")
    results = {r["case_id"]: r for r in rows}
    ids = {c["case_id"] for c in cases}
    if len(results) != len(rows) or len(ids) != len(cases) or set(results) - ids:
        raise ValueError("duplicate or unknown case_id in evaluation")
    scores, details, noanswer = [], [], []
    for case in cases:
        result = results.get(case["case_id"], {})
        retrieved = result.get("retrieved_evidence", [])
        if not isinstance(retrieved, list) or any(not isinstance(e, str) for e in retrieved):
            raise ValueError("retrieved_evidence must be a list of IDs")
        score = required_evidence_recall(case["required_evidence"], set(retrieved))
        if score is not None:
            scores.append(score)
        else:
            noanswer.append(result.get("abstained") is True)
        details.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "required_evidence_recall": score,
                "result_present": bool(result),
            }
        )
    return {
        "case_count": len(cases),
        "missing_result_count": len(ids - set(results)),
        "answerable_count": len(scores),
        "unanswerable_count": len(noanswer),
        "required_evidence_recall": sum(scores) / len(scores) if scores else None,
        "noanswer_abstention_rate": sum(noanswer) / len(noanswer) if noanswer else None,
        "quality_scope": "evidence IDs only; answer correctness requires separate review",
        "per_case": details,
    }
