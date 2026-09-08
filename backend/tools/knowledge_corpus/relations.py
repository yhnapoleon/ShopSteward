"""Author-controlled retrieval gates and exact-source intake annotations.

These are fixture annotations, never production confirmation or chunk identifiers.
No natural-language condition is parsed into code or used to infer authorization.
"""

import math


def machine_conditions_satisfied(required, context):
    if not isinstance(required, dict) or not 1 <= len(required) <= 30:
        return False
    if not isinstance(context, dict):
        return False
    for key, value in required.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            return False
        if type(value) not in (str, bool, int, float):
            return False
        if isinstance(value, str) and (not value or len(value) > 1024):
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
        if key not in context or type(context[key]) is not type(value) or context[key] != value:
            return False
    return True


def exact_source_span(authored_quote, source_text):
    """Locate authored evidence through layout whitespace, returning the exact original span."""
    positions = [i for i, c in enumerate(source_text) if not c.isspace()]
    flat = "".join(source_text[i] for i in positions)
    wanted = "".join(c for c in authored_quote if not c.isspace())
    start = flat.find(wanted)
    if not wanted or start < 0:
        return None
    return source_text[positions[start] : positions[start + len(wanted) - 1] + 1]


def intake_metadata(relation, document, authored_quote, actual_source_text):
    metadata = document["metadata"]
    # Literal fixture policy: match declared store/scenario AND caller-established evidence state.
    # The True requirement never asserts that evidence was actually supplied by a caller.
    conditions = {
        "store_fixture": metadata["store_fixture"],
        "scenario_id": metadata["scenario_id"],
        "proof_available": True,
    }
    quote = exact_source_span(authored_quote, actual_source_text)
    result = dict(
        relation,
        machine_conditions=conditions,
        evidence_quote=quote,
        condition_semantics="all_equal_required_keys_fail_closed",
        condition_authoring="explicit_fixture_policy_v1",
        evidence_chunk_ids=[],
        executable=False,
        execution_status="requires_actual_parser_quote_binding",
        assertion_scope="synthetic_fact_only_not_real_business_verification",
        retrieval_edges=[],
        retrieval_orientation="see_explicit_retrieval_edges",
    )
    if quote is None:
        result["execution_status"] = "not_executable_quote_unresolved"
        return result
    kind = relation["relation_type"]
    if kind == "APPLIES_TO":
        subject, predicate, target = (
            relation["to_entity"],
            "HAS_APPLICABLE_DOCUMENT",
            relation["from_entity"],
        )
        orientation = "declared_reverse_lookup_not_business_inverse"
    elif kind in {"SUPPLIES", "SUPERSEDES"}:
        subject, predicate, target = relation["from_entity"], kind, relation["to_entity"]
        orientation = "semantic_subject_to_object"
    else:
        result["execution_status"] = "not_executable_unsupported_relation_type"
        return result
    result["retrieval_edges"] = [
        {
            "id": relation["relation_id"] + ":lookup",
            "subject": subject,
            "predicate": predicate,
            "object": target,
            "semantic_relation_id": relation["relation_id"],
            "retrieval_orientation": orientation,
            "conditions": conditions,
            "confirmed": False,
            "evidence_chunk_ids": [],
            "source_version_fixture_id": relation["source_version_id"],
            "evidence_quote": quote,
            "meaning": "evidence discovery only; never substitution permission",
        }
    ]
    return result
