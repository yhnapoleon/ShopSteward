"""Contract tests: reject leakage, fabricated provenance and overwritten originals."""

import hashlib
import json

import pytest

from tools.knowledge_corpus.evaluation import evaluate, required_evidence_recall
from tools.knowledge_corpus.manifest import build_manifest, logical_count, validate_manifest
from tools.knowledge_corpus.ownership import write_owned
from tools.knowledge_corpus.validate import (
    read_jsonl,
    validate_case_splits,
    validate_scenario,
    validate_source,
)


def test_public_agent_aliases_are_normalized_without_inventing_acquisition(tmp_path):
    from tools.knowledge_corpus.manifest import normalize_public

    item = record(tmp_path)
    raw = source() | {
        "acquisition_status": "acquired",
        "source_kind": "official_web_archive",
        "original_path": item["original_path"],
        "content_sha256": item["sha256"],
        "size_bytes": item["size"],
        "mime": item["mime"],
        "document_fixture_id": "P1",
        "version_fixture_id": "P1-v1",
        "source_url": "https://example.org/manual",
    }
    normalized = normalize_public(raw)
    assert normalized["size"] == 44
    assert normalized["scenario_family_id"] is None
    assert normalized["synthetic"] is False
    assert normalized["metadata"]["source_url"] == raw["source_url"]


def test_each_rendered_format_resolves_evidence_to_actual_text():
    from tools.knowledge_corpus.render import extract_sections, render_document

    sections = [{"heading": "商业决定", "text": "模拟：缺少封签照片时仅登记争议，不自动退款。"}]
    for extension in ["md", "txt", "csv", "docx", "xlsx", "pdf"]:
        data, locators = render_document("模拟验收", sections, extension)
        extracted = extract_sections(data, extension)
        assert sections[0]["text"] in extracted[locators[0]]
        assert render_document("模拟验收", sections, extension)[0] == data


def test_near_duplicate_comparison_removes_ids_and_numbers():
    from tools.knowledge_corpus.quality import near_duplicates

    rows = [
        dict(id="A", text="模拟 STORE001 SKU003 配送条款：未收到签章则暂缓付款。"),
        dict(id="B", text="模拟 STORE009 SKU008 配送条款：未收到签章则暂缓付款。"),
        dict(id="C", text="活动赠品仅限自提核销，退款后撤销领取资格。"),
    ]
    assert [(r["left"], r["right"]) for r in near_duplicates(rows)] == [("A", "B")]


def test_expanded_build_keeps_gold_out_and_counts_real_revisions(tmp_path):
    from tools.knowledge_corpus.builder import build

    full = build(tmp_path, "full")
    assert full["counts"]["logical_document_count"] == 900
    assert full["counts"]["version_count"] == 1100
    assert full["public_gap"] == 100
    assert full["counts"]["chunk_count"] is None
    pilot = json.loads((tmp_path / "manifests/pilot.json").read_text(encoding="utf-8"))
    assert pilot["counts"]["logical_document_count"] == 180
    assert pilot["public_gap"] == 20
    cases = read_jsonl(tmp_path / "cases.jsonl")
    assert len(cases) == 300
    assert sum(c["split"] == "dev" for c in cases) == 100
    requests = read_jsonl(tmp_path / "queries-dev.jsonl")
    assert len(requests) == 100
    assert {q["case_id"] for q in requests} == {c["case_id"] for c in cases if c["split"] == "dev"}
    assert all(q["split"] == "dev" and "required_evidence" not in q for q in requests)
    assert sum(bool(c["relation_tags"]) for c in cases) == 60
    validate_case_splits(cases)
    for document in full["documents"]:
        assert "facts" not in document["metadata"]
        assert "required_evidence" not in document["metadata"]
    before = (tmp_path / "freeze-evidence.json").read_bytes()
    assert build(tmp_path, "full")["counts"] == full["counts"]
    assert (tmp_path / "freeze-evidence.json").read_bytes() == before


def test_corrupted_evidence_locator_and_relation_provenance_fail(tmp_path):
    from tools.knowledge_corpus.builder import build
    from tools.knowledge_corpus.quality import verify_evaluation

    build(tmp_path, "full")
    path = tmp_path / "facts/evidence.jsonl"
    rows = read_jsonl(path)
    rows[0]["locator"] = "nonexistent-section"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    requests = read_jsonl(tmp_path / "queries-dev.jsonl")
    requests[0]["expected_answer"] = "must not leak"
    (tmp_path / "queries-dev.jsonl").write_text(
        "\n".join(json.dumps(r) for r in requests), encoding="utf-8"
    )
    result = verify_evaluation(tmp_path)
    assert any("locator" in e for e in result["errors"])
    assert any("dev requests" in e for e in result["errors"])


def test_freeze_and_unowned_file_are_not_overwritten(tmp_path):
    from tools.knowledge_corpus.builder import build

    (tmp_path / "cases.jsonl").write_text("hand-authored", encoding="utf-8")
    with pytest.raises(ValueError, match="ownership"):
        build(tmp_path, "pilot")
    assert (tmp_path / "cases.jsonl").read_text() == "hand-authored"


def source():
    return dict(
        source_family_id="P1",
        title="Manual",
        publisher="Example",
        url="https://example.org/manual",
        language="en",
        jurisdiction="HK",
        publication_date=None,
        retrieved_at="2026-09-08T00:00:00Z",
        acquisition_status="reference_only",
        use_terms_status="review_pending",
        source_kind="reference_card",
        synthetic=False,
    )


def test_paraphrase_family_cannot_cross_splits():
    with pytest.raises(ValueError, match="family"):
        validate_case_splits(
            [
                dict(case_id="Q1", scenario_family_id="S1", split="dev"),
                dict(case_id="Q2", scenario_family_id="S1", split="test"),
            ]
        )


def test_source_family_cannot_leak_even_if_scenario_names_differ():
    with pytest.raises(ValueError, match="family"):
        validate_case_splits(
            [
                dict(case_id="Q1", scenario_family_id="S1", source_family_ids=["P"], split="dev"),
                dict(case_id="Q2", scenario_family_id="S2", source_family_ids=["P"], split="test"),
            ]
        )


def test_unknown_publication_date_is_explicit_not_missing():
    assert validate_source(source())["publication_date"] is None
    row = source()
    del row["publication_date"]
    with pytest.raises(ValueError, match="publication_date"):
        validate_source(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_date", "2026-02-31"),
        ("retrieved_at", "yesterday"),
        ("original_path", "public/fake.md"),
        ("content_sha256", "0" * 64),
    ],
)
def test_reference_cannot_claim_original_or_invalid_dates(field, value):
    row = source() | {field: value}
    with pytest.raises(ValueError):
        validate_source(row)


def test_jsonl_error_identifies_file_and_line_without_echoing_input(tmp_path):
    path = tmp_path / "source.jsonl"
    path.write_text(json.dumps(source()) + '\n{"secret":"do-not-echo"', encoding="utf-8")
    with pytest.raises(ValueError, match=r"source.jsonl:2") as error:
        read_jsonl(path, validate_source)
    assert "do-not-echo" not in str(error.value)


def test_owned_write_rejects_escape_and_manual_edits(tmp_path):
    with pytest.raises(ValueError, match="path"):
        write_owned(tmp_path, "../outside.md", b"bad", None)
    sha = write_owned(tmp_path, "originals/a.md", b"original", None)
    assert write_owned(tmp_path, "originals/a.md", b"revision", sha)
    (tmp_path / "originals/a.md").write_bytes(b"manual")
    with pytest.raises(ValueError, match="modified|ownership"):
        write_owned(tmp_path, "originals/a.md", b"overwrite", sha)
    assert (tmp_path / "originals/a.md").read_bytes() == b"manual"


def test_untracked_existing_file_cannot_be_adopted(tmp_path):
    (tmp_path / "a").write_bytes(b"same")
    with pytest.raises(ValueError, match="ownership"):
        write_owned(tmp_path, "a", b"same", None)


def test_versions_are_not_independent_documents():
    assert (
        logical_count(
            [
                dict(document_fixture_id="D1", version_fixture_id="V1"),
                dict(document_fixture_id="D1", version_fixture_id="V2"),
            ]
        )
        == 1
    )


def record(tmp_path):
    (tmp_path / "originals").mkdir(exist_ok=True)
    data = b"Business decision: reject incompatible lids."
    (tmp_path / "originals/a.md").write_bytes(data)
    return dict(
        document_fixture_id="D1",
        version_fixture_id="D1-v1",
        original_path="originals/a.md",
        mime="text/markdown",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_family_id="S1",
        scenario_family_id="F1",
        metadata={"category": "product"},
        synthetic=True,
    )


def test_manifest_excludes_reference_and_rejects_gold(tmp_path):
    item = record(tmp_path)
    assert build_manifest([item, source()], tmp_path)["counts"]["logical_document_count"] == 1
    bad = item | {"original_path": "facts/gold.md"}
    with pytest.raises(ValueError, match="ingest|original"):
        build_manifest([bad], tmp_path)
    with pytest.raises(ValueError, match="gold"):
        build_manifest([item | {"metadata": {"expected_answer": "leak"}}], tmp_path)


def test_manifest_detects_changed_bytes_and_forged_count(tmp_path):
    manifest = build_manifest([record(tmp_path)], tmp_path)
    manifest["counts"]["logical_document_count"] = 1000
    (tmp_path / "originals/a.md").write_bytes(b"changed")
    result = validate_manifest(manifest, tmp_path)
    assert result["logical_document_count"] == 1
    assert any("sha256" in e for e in result["errors"])
    assert any("counts" in e for e in result["errors"])


def test_one_of_two_conditions_is_not_complete_support():
    assert required_evidence_recall([{"A", "A2"}, {"B"}], {"A2"}) == 0.5
    assert required_evidence_recall([], {"unrelated"}) is None


def test_missing_retrieval_rows_are_not_silently_removed_from_denominator(tmp_path):
    cases = tmp_path / "cases.jsonl"
    results = tmp_path / "results.jsonl"
    cases.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                dict(case_id="Q1", required_evidence=[["A"]], group="exact"),
                dict(case_id="Q2", required_evidence=[["B"]], group="exact"),
            ]
        ),
        encoding="utf-8",
    )
    results.write_text(json.dumps(dict(case_id="Q1", retrieved_evidence=["A"])), encoding="utf-8")
    scored = evaluate(results, cases)
    assert scored["required_evidence_recall"] == 0.5
    assert scored["missing_result_count"] == 1


def test_synthetic_fact_must_have_units_and_marker():
    row = dict(
        scenario_family_id="S1",
        synthetic=True,
        store_fixture="STORE1",
        entity_refs=["SKU1"],
        effective_interval={"from": "2026-01-01", "until": "2027-01-01"},
        facts=[dict(fact_id="F", kind="synthetic", text="模拟两箱", value=2)],
        exceptions=[],
        document_kinds=["supplier"],
    )
    with pytest.raises(ValueError, match="unit"):
        validate_scenario(row)


def test_freeze_rejects_original_changes_even_if_questions_stay_identical():
    from tools.knowledge_corpus.ownership import validate_freeze

    previous = {
        "stage": "full",
        "files": {"cases.jsonl": "a", "originals/a.md": "b"},
        "public_originals": {"public/a.md": "c"},
    }
    proposed = {
        "stage": "full",
        "files": {"cases.jsonl": "a", "originals/a.md": "changed"},
        "public_originals": {"public/a.md": "c"},
    }
    with pytest.raises(ValueError, match="frozen"):
        validate_freeze(previous, proposed)
    proposed["files"]["originals/a.md"] = "b"
    proposed["public_originals"]["public/a.md"] = "changed"
    with pytest.raises(ValueError, match="frozen"):
        validate_freeze(previous, proposed)


def test_no_actual_retrieval_results_do_not_produce_an_effectiveness_score(tmp_path):
    cases = tmp_path / "cases.jsonl"
    results = tmp_path / "results.jsonl"
    cases.write_text(json.dumps(dict(case_id="Q", group="exact", required_evidence=[["A"]])))
    results.write_text("")
    with pytest.raises(ValueError, match="actual retrieval"):
        evaluate(results, cases)


def test_public_archive_hash_is_checked_even_when_normalized_text_is_intact(tmp_path):
    item = record(tmp_path)
    (tmp_path / "public").mkdir()
    (tmp_path / "public/archive.pdf").write_bytes(b"altered archive")
    item["metadata"].update(
        source_original_path="public/archive.pdf",
        source_original_sha256=hashlib.sha256(b"original archive").hexdigest(),
    )
    result = validate_manifest(build_manifest([item], tmp_path), tmp_path)
    assert any("source original sha256" in e for e in result["errors"])


def test_pilot_already_declares_the_planned_revision_boundary(tmp_path):
    from tools.knowledge_corpus.builder import build

    pilot = build(tmp_path, "pilot")
    assert pilot["documents"][0]["metadata"]["valid_until"] == "2026-01-16T00:00:00Z"


def test_relation_intake_is_explicit_oriented_and_not_confirmed_before_chunk_binding():
    from tools.knowledge_corpus.relations import intake_metadata

    relation = dict(
        relation_id="R1",
        relation_type="APPLIES_TO",
        from_entity="V1",
        to_entity="SKU001",
        source_version_id="V1",
        evidence_id="E1",
        locator="section:1",
        conditions=["arbitrary prose is not executable code"],
    )
    document = dict(metadata=dict(store_fixture="STORE01", scenario_id="F01-B1"))
    text = "模拟供货事实：SUP01提供SKU001。\n本说明适用于SKU001。"
    enriched = intake_metadata(relation, document, text.replace("\n", ""), text)
    assert enriched["machine_conditions"] == {
        "store_fixture": "STORE01",
        "scenario_id": "F01-B1",
        "proof_available": True,
    }
    assert enriched["evidence_quote"] == text
    assert enriched["executable"] is False
    assert enriched["evidence_chunk_ids"] == []
    edge = enriched["retrieval_edges"][0]
    assert (edge["subject"], edge["predicate"], edge["object"]) == (
        "SKU001",
        "HAS_APPLICABLE_DOCUMENT",
        "V1",
    )
    assert enriched["from_entity"] == "V1"
    assert enriched["to_entity"] == "SKU001"
    assert edge["retrieval_orientation"] == "declared_reverse_lookup_not_business_inverse"


def test_relation_machine_conditions_missing_false_or_wrong_scalar_type_fail_closed():
    from tools.knowledge_corpus.relations import machine_conditions_satisfied

    required = {"store_fixture": "STORE01", "proof_available": True}
    assert machine_conditions_satisfied(
        required, dict(store_fixture="STORE01", proof_available=True)
    )
    for context in [
        {},
        {"store_fixture": "STORE01"},
        {"store_fixture": "STORE01", "proof_available": False},
        {"store_fixture": "STORE01", "proof_available": 1},
    ]:
        assert not machine_conditions_satisfied(required, context)
    assert not machine_conditions_satisfied({}, {})
    assert not machine_conditions_satisfied({"x": []}, {"x": []})


def test_unresolved_quote_never_creates_an_executable_relation():
    from tools.knowledge_corpus.relations import intake_metadata

    relation = dict(
        relation_id="R",
        relation_type="SUPPLIES",
        from_entity="SUP",
        to_entity="SKU",
        source_version_id="V",
        evidence_id="E",
        locator="page:1",
    )
    result = intake_metadata(
        relation,
        {"metadata": {"store_fixture": "STORE01", "scenario_id": "S"}},
        "missing evidence",
        "unrelated actual source",
    )
    assert result["evidence_quote"] is None
    assert result["execution_status"] == "not_executable_quote_unresolved"
    assert result["retrieval_edges"] == []


def test_relation_metadata_upgrade_cannot_change_queries_or_originals():
    from tools.knowledge_corpus.ownership import validate_freeze

    previous = {
        "stage": "full",
        "evaluation_version": "expanded-v1",
        "files": {"cases.jsonl": "q", "originals/a.md": "a", "relations.jsonl": "old"},
        "public_originals": {},
    }
    proposed = {
        "stage": "full",
        "evaluation_version": "expanded-v1.1",
        "revision_reason": "Add explicit relation intake metadata; queries unchanged",
        "files": {"cases.jsonl": "q", "originals/a.md": "a", "relations.jsonl": "new"},
        "public_originals": {},
    }
    validate_freeze(previous, proposed)
    proposed["files"]["cases.jsonl"] = "changed"
    with pytest.raises(ValueError, match="frozen"):
        validate_freeze(previous, proposed)


def test_current_agent_subset_never_redates_expired_documents_or_frozen_questions():
    from copy import deepcopy

    from tools.knowledge_corpus.temporal import current_agent_subset

    def doc(ident, start, end, scenario):
        return dict(
            document_fixture_id=ident,
            version_fixture_id=ident + "-v1",
            synthetic=True,
            metadata=dict(valid_from=start, valid_until=end, scenario_id=scenario),
        )

    manifest = {
        "documents": [
            doc("OLD", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "S1"),
            doc("CURRENT", "2026-09-01T00:00:00Z", "2026-09-16T00:00:00Z", "S2"),
        ]
    }
    cases = [
        dict(
            case_id="Q1",
            scenario_id="S1",
            as_of="2026-01-10",
            query="2026-01-10 old",
            required_evidence=[["OLD-v1:E1"]],
        ),
        dict(
            case_id="Q2",
            scenario_id="S2",
            as_of="2026-09-10",
            query="2026-09-10 current",
            required_evidence=[["CURRENT-v1:E1"]],
        ),
    ]
    before = deepcopy((manifest, cases))
    result = current_agent_subset(manifest, cases, "2026-09-08T00:00:00+08:00")
    assert [d["document_fixture_id"] for d in result["documents"]] == ["CURRENT"]
    assert len(result["cases"]) == 1
    assert result["cases"][0]["query"] == "2026-09-08 current"
    assert result["cases"][0]["source_case_id"] == "Q2"
    assert result["cases"][0]["quality_evaluation_member"] is False
    assert (manifest, cases) == before
    assert current_agent_subset(manifest, cases, "2026-09-16T00:00:00Z")["documents"] == []


def test_csv_has_a_real_header_and_rectangular_metadata_and_business_rows():
    import csv
    import io

    from tools.knowledge_corpus.render import extract_sections, render_document

    sections = [
        {"heading": "举证", "text": "模拟：先留照片，再登记争议。"},
        {"heading": "例外", "text": "模拟：签收不等于索赔获准。"},
    ]
    data, locators = render_document("模拟争议单", sections, "csv")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0] == ["section", "heading", "text"]
    assert {len(row) for row in rows} == {3}
    assert locators == ["row:3:C", "row:4:C"]
    assert extract_sections(data, "csv")["row:3:C"] == sections[0]["text"]


def test_csv_repair_upgrade_still_rejects_changes_to_business_documents_and_questions():
    from tools.knowledge_corpus.ownership import validate_freeze

    previous = {
        "stage": "full",
        "evaluation_version": "expanded-v1.1",
        "files": {"originals/a.csv": "old", "originals/b.md": "same", "cases.jsonl": "q"},
        "public_originals": {},
    }
    proposed = {
        "stage": "full",
        "evaluation_version": "expanded-v1.2",
        "revision_reason": "CSV repair",
        "files": {"originals/a.csv": "new", "originals/b.md": "same", "cases.jsonl": "q"},
        "public_originals": {},
    }
    validate_freeze(previous, proposed)
    proposed["files"]["originals/b.md"] = "changed"
    with pytest.raises(ValueError, match="frozen"):
        validate_freeze(previous, proposed)


def test_external_check_distinguishes_new_acquisitions_from_modified_borrowed_files():
    from tools.knowledge_corpus.ownership import compare_existing_files

    before = {"public/original.pdf": "hash", "originals/a.md": "synthetic"}
    after = before | {"public/expansion/new.pdf": "newhash"}
    result = compare_existing_files(before, after)
    assert result["unchanged"] is True
    assert result["added_files"] == ["public/expansion/new.pdf"]
    after["public/original.pdf"] = "modified"
    result = compare_existing_files(before, after)
    assert result["unchanged"] is False
    assert result["changed_or_missing_files"] == ["public/original.pdf"]


def test_dev_query_export_whitelists_requests_and_excludes_test_and_nested_gold():
    from tools.knowledge_corpus.evaluation import export_queries

    rows = [
        dict(
            case_id="D",
            split="dev",
            query="Which evidence applies?",
            store_fixture="STORE01",
            as_of="2026-09-10",
            entry_entities=["SUP01"],
            query_constraints={"proof_available": False, "expected_answer": "secret"},
            required_evidence=[["GOLD"]],
            group="unanswerable",
            expected_path=["hidden"],
        ),
        dict(
            case_id="T",
            split="test",
            query="frozen test question",
            store_fixture="STORE01",
            as_of="2026-09-10",
        ),
    ]
    exported = export_queries(rows)
    assert exported == [
        dict(
            case_id="D",
            split="dev",
            query="Which evidence applies?",
            store_fixture="STORE01",
            as_of="2026-09-10",
            entry_entities=["SUP01"],
            query_constraints={"proof_available": False},
        )
    ]
    assert all(
        word not in json.dumps(exported)
        for word in ["GOLD", "secret", "hidden", "group", "required_evidence"]
    )


def test_dev_export_is_sorted_and_accepted_by_actual_benchmark_loader(tmp_path):
    import importlib.util
    from pathlib import Path

    from tools.knowledge_corpus.builder import jsonl_bytes
    from tools.knowledge_corpus.evaluation import export_queries

    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "corpus_benchmark", repo / "knowledge/tools/benchmark.py"
    )
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(build_manifest([record(tmp_path)], tmp_path)), encoding="utf-8"
    )
    rows = [
        dict(
            case_id=key,
            split="dev",
            query="Which terms apply?",
            as_of="2026-09-10",
            store_fixture="STORE01",
            entry_entities=["SUP01"],
        )
        for key in ["B", "A"]
    ]
    request_path = tmp_path / "queries-dev.jsonl"
    request_path.write_bytes(jsonl_bytes(export_queries(rows)))
    assert request_path.read_bytes() == jsonl_bytes(export_queries(list(reversed(rows))))
    loaded = benchmark.load_inputs(manifest_path, request_path, root=tmp_path)
    assert [q["case_id"] for q in loaded["queries"]] == ["A", "B"]
    assert loaded["queries"][0]["as_of"] == "2026-09-10T00:00:00+00:00"


def test_dev_export_rejects_duplicate_ids_and_nested_request_values():
    from tools.knowledge_corpus.evaluation import export_queries

    row = dict(
        case_id="D",
        split="dev",
        query="Which terms apply?",
        as_of="2026-09-10",
        store_fixture="STORE01",
        query_constraints={"proof_available": False},
    )
    with pytest.raises(ValueError, match="duplicate"):
        export_queries([row, row])
    with pytest.raises(ValueError, match="constraint"):
        export_queries([row | {"query_constraints": {"proof_available": {"gold": "secret"}}}])


def test_manifest_rejects_ragged_csv_even_with_matching_hash(tmp_path):
    item = record(tmp_path)
    data = b"section,heading,text\nmetadata,title\n1,terms,hello\n"
    (tmp_path / "originals/ragged.csv").write_bytes(data)
    item.update(
        original_path="originals/ragged.csv",
        mime="text/csv",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    result = validate_manifest(build_manifest([item], tmp_path), tmp_path)
    assert any("CSV" in error for error in result["errors"])
