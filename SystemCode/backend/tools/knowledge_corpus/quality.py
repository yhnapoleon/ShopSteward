"""Byte-backed evidence, family, entity, version, duplicate and freeze auditing."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .evaluation import export_queries
from .manifest import validate_manifest
from .ownership import digest, safe_path
from .relations import intake_metadata, machine_conditions_satisfied
from .render import extract_sections
from .validate import (
    read_jsonl,
    validate_case,
    validate_case_splits,
    validate_scenario,
    validate_source,
)


def normalize(text):
    text = re.sub(r"\b(?:STORE|SKU|SUP)\d+\b|SYN-[A-Za-z0-9:-]+|F\d+-B\d+", "", text)
    text = re.sub(r"\d+(?:\.\d+)?", "", text)
    return re.sub(r"\s+|模拟|SYNTHETIC|[，。；：、（）/；]", "", text)


def near_duplicates(rows, threshold=0.85):
    """Exact 5-gram Jaccard after ID/number stripping and recurring sentence removal.

    Frequent whole sentences are corpus boilerplate; short records remain comparable.
    Length bound is lossless for Jaccard and avoids most irrelevant intersections.
    """
    sentences = [re.split(r"[。\n]", row["text"]) for row in rows]
    frequency = Counter(s for parts in sentences for s in set(normalize(p) for p in parts) if s)
    grams = []
    for row, parts in zip(rows, sentences, strict=True):
        text = "。".join(p for p in parts if frequency[normalize(p)] < max(10, len(rows) // 20))
        value = normalize(text)
        if len(value) < 5:
            value = normalize(row["text"])
        grams.append({value[i : i + 5] for i in range(max(1, len(value) - 4))})
    result = []
    for i, left in enumerate(grams):
        for j in range(i + 1, len(grams)):
            right = grams[j]
            if min(len(left), len(right)) < threshold * max(len(left), len(right)):
                continue
            intersection = len(left & right)
            score = intersection / (len(left) + len(right) - intersection) if left or right else 1.0
            if score >= threshold:
                result.append(
                    {
                        "left": rows[i]["id"],
                        "right": rows[j]["id"],
                        "jaccard": round(score, 6),
                        "review_status": "pending",
                        "same_scenario": rows[i].get("scenario_id") == rows[j].get("scenario_id"),
                    }
                )
    return result


def _plain(text):
    return re.sub(r"\s+", "", text)


def verify_evaluation(root):
    root = Path(root)
    errors = []
    cases = read_jsonl(root / "cases.jsonl", validate_case)
    requests = read_jsonl(root / "queries-dev.jsonl")
    if requests != export_queries(cases):
        errors.append("dev requests differ from the gold-free frozen-case projection")
    scenarios = read_jsonl(root / "scenarios.jsonl", validate_scenario)
    sources = read_jsonl(root / "sources.jsonl", validate_source)
    evidence = read_jsonl(root / "facts/evidence.jsonl")
    relations = read_jsonl(root / "relations.jsonl")
    entities = json.loads((root / "entities-fixture.json").read_text(encoding="utf-8"))
    manifest_path = root / "manifests/full.json"
    if not manifest_path.exists():
        manifest_path = root / "manifests/pilot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors.extend(validate_manifest(manifest, root)["errors"])
    try:
        validate_case_splits(cases)
    except ValueError as error:
        errors.append(str(error))
    versions = {d["version_fixture_id"]: d for d in manifest["documents"]}
    scenario_by_id = {s["scenario_id"]: s for s in scenarios}
    source_families = {s["source_family_id"] for s in sources}
    entity_ids = {
        e["fixture_id"] for kind in ("stores", "suppliers", "skus") for e in entities[kind]
    }
    skus = {s["fixture_id"]: s for s in entities["skus"]}
    for scenario in scenarios:
        if scenario["store_fixture"] not in entity_ids or set(scenario["entity_refs"]) - entity_ids:
            errors.append("scenario entity reference missing: " + scenario["scenario_id"])
        for sku in scenario["sku_fixture_ids"]:
            if skus[sku]["supplier_fixture_id"] != scenario["supplier_fixture_id"]:
                errors.append("scenario supplier/SKU association inconsistent")
    by_document = defaultdict(list)
    for version in versions.values():
        if version["source_family_id"] not in source_families:
            errors.append("document source reference missing")
        if version["synthetic"]:
            metadata = version["metadata"]
            if metadata["scenario_id"] not in scenario_by_id:
                errors.append("document scenario reference missing")
            if set(metadata["entity_refs"]) - entity_ids:
                errors.append("document entity reference missing")
            by_document[version["document_fixture_id"]].append(version)
    for chain in by_document.values():
        chain.sort(key=lambda r: r["metadata"]["revision_number"])
        for prior, current in zip(chain, chain[1:], strict=False):
            if (
                current["metadata"]["supersedes"] != prior["version_fixture_id"]
                or prior["metadata"]["valid_until"] != current["metadata"]["valid_from"]
            ):
                errors.append("version chain continuity/supersedes mismatch")
            if current["sha256"] == prior["sha256"]:
                errors.append("revision has no content change")
    evidence_by_id = {e["evidence_id"]: e for e in evidence}
    if len(evidence_by_id) != len(evidence):
        errors.append("duplicate evidence ID")
    extracted = {}
    for item in evidence:
        version = versions.get(item["source_version_id"])
        if version is None:
            errors.append("evidence version missing: " + item["evidence_id"])
            continue
        try:
            if item["source_version_id"] not in extracted:
                data = safe_path(root, version["original_path"]).read_bytes()
                extracted[item["source_version_id"]] = extract_sections(
                    data, Path(version["original_path"]).suffix[1:]
                )
            actual = extracted[item["source_version_id"]].get(item["locator"])
            if actual is None or _plain(item["quote"]) not in _plain(actual):
                errors.append("evidence locator/quote does not resolve: " + item["evidence_id"])
            if item["original_sha256"] != version["sha256"]:
                errors.append("evidence original sha256 mismatch")
            if item["content_sha256"] != digest(item["quote"].encode("utf-8")):
                errors.append("evidence content sha256 mismatch")
        except (ValueError, OSError):
            errors.append("evidence extraction failed: " + item["evidence_id"])
    for relation in relations:
        ev = evidence_by_id.get(relation["evidence_id"])
        if (
            ev is None
            or relation["source_version_id"] != ev["source_version_id"]
            or relation["locator"] != ev["locator"]
        ):
            errors.append("relation provenance/locator mismatch: " + relation["relation_id"])
            continue
        if relation["assertion_status"] != "synthetic_verified":
            errors.append("synthetic relation status must not claim real verified")
        actual_text = extracted[ev["source_version_id"]].get(ev["locator"], "")
        proposed = intake_metadata(
            relation, versions[ev["source_version_id"]], ev["quote"], actual_text
        )
        for key in ("machine_conditions", "evidence_quote", "retrieval_edges", "execution_status"):
            if relation.get(key) != proposed[key]:
                errors.append("relation intake annotation mismatch: " + relation["relation_id"])
        if not machine_conditions_satisfied(
            relation.get("machine_conditions"), relation.get("machine_conditions")
        ):
            errors.append("relation machine conditions missing or invalid")
        if relation.get("executable") is not False or relation.get("evidence_chunk_ids") != []:
            errors.append("fixture must not fabricate parser binding/confirmation")
        if not relation.get("evidence_quote") or relation["evidence_quote"] not in actual_text:
            errors.append("relation evidence quote is not an exact source substring")
        if (
            relation["from_entity"] not in entity_ids | versions.keys()
            or relation["to_entity"] not in entity_ids | versions.keys()
        ):
            errors.append("relation endpoint missing")
        if (
            not relation["conditions"]
            or relation["effective_interval"]["from"] >= relation["effective_interval"]["until"]
        ):
            errors.append("relation conditions/interval missing or invalid")
    for case in cases:
        scenario = scenario_by_id.get(case["scenario_id"])
        if scenario is None or scenario["scenario_family_id"] != case["scenario_family_id"]:
            errors.append("case scenario family mismatch")
        for alternatives in case["required_evidence"]:
            for evidence_id in alternatives:
                ev = evidence_by_id.get(evidence_id)
                if ev is None:
                    errors.append("case evidence missing: " + evidence_id)
                    continue
                document = versions[ev["source_version_id"]]
                metadata = document["metadata"]
                if (
                    metadata["store_fixture"] != case["store_fixture"]
                    or not metadata["valid_from"][:10]
                    <= case["as_of"]
                    < metadata["valid_until"][:10]
                ):
                    errors.append("case evidence wrong store/effective version")
        if any(e["evidence_id"] in case["query"] for e in evidence):
            errors.append("query leaks gold evidence ID")
    freeze = json.loads((root / "freeze-evidence.json").read_text(encoding="utf-8"))
    for relative, sha in (freeze["files"] | freeze["public_originals"]).items():
        path = safe_path(root, relative)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            errors.append("frozen file hash mismatch: " + relative)
    expected_groups = {
        "exact": 40,
        "keyword": 40,
        "semantic": 60,
        "cross_document": 60,
        "unanswerable": 40,
        "hybrid": 60,
    }
    group_counts, split_counts = (
        dict(Counter(c["group"] for c in cases)),
        dict(Counter(c["split"] for c in cases)),
    )
    tagged = sum(bool(c["relation_tags"]) for c in cases)
    if manifest["stage"] == "full" and (
        group_counts != expected_groups or split_counts != {"dev": 100, "test": 200} or tagged != 60
    ):
        errors.append("full evaluation group/split/relation quota mismatch")
    return {
        "errors": errors,
        "case_count": len(cases),
        "dev_request_count": len(requests),
        "dev_requests_sha256": digest((root / "queries-dev.jsonl").read_bytes()),
        "group_counts": group_counts,
        "split_counts": split_counts,
        "relation_case_count": tagged,
        "relation_edge_count": len(relations),
        "evidence_count": len(evidence),
        "scenario_count": len(scenarios),
        "scenario_family_count": len({s["scenario_family_id"] for s in scenarios}),
        "human_review": "pending",
        "model_or_retrieval_scores": None,
    }
