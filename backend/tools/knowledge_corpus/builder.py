"""Deterministic authored corpus assembly. Writes only paths in its ownership ledger."""

# Authored Chinese paragraphs deliberately stay intact for editorial review.
# ruff: noqa: E501
import csv
import io
import json
from pathlib import Path

from .catalog import TEXT, families
from .evaluation import export_queries
from .manifest import build_manifest, normalize_public, validate_manifest
from .ownership import digest, safe_path, validate_freeze, write_owned
from .questions import query_plan
from .relations import intake_metadata
from .render import MIMES, extract_sections, render_document
from .schema import SCHEMA
from .temporal import current_agent_subset
from .validate import (
    read_jsonl,
    validate_case,
    validate_case_splits,
    validate_scenario,
    validate_source,
)

ROOT = Path(__file__).resolve().parents[3] / "docs/evaluation/knowledge-expanded"
QUOTAS = {"supplier": 180, "product": 320, "sop": 160, "campaign": 100, "retro": 140}
LABELS = {
    "supplier": "供货附件",
    "product": "商品与包装说明",
    "sop": "当班操作规程",
    "campaign": "活动执行要求",
    "retro": "异常复盘记录",
}
FORMATS = tuple(MIMES)
OWNER = "shopsteward-expanded-v1"
REVISION_COUNT = 200


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def jsonl_bytes(rows):
    return (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n"
    ).encode("utf-8")


def entities():
    stores = [
        {"fixture_id": f"STORE{i:02}", "name": f"模拟门店{i:02}", "synthetic": True}
        for i in range(1, 9)
    ]
    suppliers = [
        {"fixture_id": f"SUP{i:02}", "name": f"模拟供应商{i:02}", "synthetic": True}
        for i in range(1, 41)
    ]
    skus = [
        {
            "fixture_id": f"SKU{i + 1:03}",
            "name": f"模拟商品{i + 1:03}",
            "synthetic": True,
            "supplier_fixture_id": f"SUP{(i // 2) % 40 + 1:02}",
            "store_fixture_ids": [f"STORE{(i // 2) % 8 + 1:02}"],
        }
        for i in range(300)
    ]
    return {
        "schema_version": "expanded-v1",
        "identity_scope": "fixtures_require_test_tenant_mapping",
        "stores": stores,
        "suppliers": suppliers,
        "skus": skus,
    }


def _interval(month):
    return {
        "from": f"2026-{month:02}-01",
        "until": f"2026-{month + 1:02}-01" if month < 12 else "2027-01-01",
    }


def scenario_rows():
    rows = []
    catalog = families()
    for branch_index in range(5):
        for family_index, family in enumerate(catalog):
            slot = branch_index * 30 + family_index
            branch = family["branches"][branch_index]
            scenario_id = f"{family['family_id']}-B{branch_index + 1}"
            interval = _interval(slot % 12 + 1)
            row = {
                "scenario_id": scenario_id,
                "scenario_family_id": family["family_id"],
                "synthetic": True,
                "store_fixture": f"STORE{slot % 8 + 1:02}",
                "supplier_fixture_id": f"SUP{slot % 40 + 1:02}",
                "sku_fixture_ids": [f"SKU{slot * 2 + 1:03}", f"SKU{slot * 2 + 2:03}"],
                "effective_interval": interval,
                "facts": [
                    {
                        "fact_id": scenario_id + "-decision",
                        "kind": "synthetic",
                        "text": "模拟：" + branch["condition"] + "；" + branch["decision"],
                    },
                    {
                        "fact_id": scenario_id + "-count",
                        "kind": "synthetic",
                        "synthetic": True,
                        "text": f"模拟盘点演练清单为{(slot % 7 + 1) * 6}件，仅用于本次交接演练。",
                        "value": (slot % 7 + 1) * 6,
                        "unit": "件",
                    },
                ],
                "exceptions": [branch["exception"]],
                "document_kinds": [
                    kind
                    for kind, total in QUOTAS.items()
                    if (slot + 1) * total // 150 > slot * total // 150
                ],
                "author": "Codex assistant, manually specified scenario catalog",
                "generation_method": "deterministic authored scenario composition; no external LLM run",
                "generation_input_sha256": digest(TEXT.encode("utf-8")),
            }
            row["entity_refs"] = [row["supplier_fixture_id"], *row["sku_fixture_ids"]]
            rows.append(validate_scenario(row))
    return rows


def _sections(family, branch, scenario, kind, ordinal, version, previous):
    store, supplier = scenario["store_fixture"], scenario["supplier_fixture_id"]
    first, second = scenario["sku_fixture_ids"]
    clause = family["clauses"][kind]
    # Additional documents have different business purposes, never just another serial number.
    if ordinal == 2:
        clause = {
            "supplier": f"争议结算补充：{branch['proof']}应分别标记已取得与待补交。采购先核供方确认范围，再决定争议行是补交、撤销还是待协商；本附件不承诺赔偿金额。{branch['exception']}。",
            "product": f"商品识别与交接附录：针对{branch['situation']}，保留{branch['proof']}作为核对材料。标识发生变化时，先核真实型号和用途，再登记原件与后续包装的对应；身份未确认的商品不得沿用另一批的批准结论。",
            "sop": f"恢复与交班补充：{branch['decision']}完成后由接班员复核{branch['proof']}是否齐全；只完成现场动作而资料未回传时保持待核，不直接关闭异常。交班要交待下一责任人与尚未确认的范围。",
        }[kind]
    elif ordinal == 3:
        clause = (
            f"适用变更说明：{branch['exception']}。这一限制用于审核改版后的商品是否仍能承接原用途。"
            "资料发布、实际采纳和营业放行是分别确认的动作；缺少变更批准时保留原用途边界，不用上传时间替代生效时间。"
        )
    roles = {
        "supplier": f"采购要求供方在回执中明确：{branch['decision']}。未得到范围确认的行仍是待协商，不因门店已经着急用货就改成已履约。",
        "product": f"使用者面对{branch['situation']}时，须将商品用途限定为已核实范围：{branch['decision']}。本说明的判断仅针对列出的商品组合，不向相似外观或相邻批次外推。",
        "sop": f"当班员工先记录{branch['condition']}，随后执行：{branch['decision']}。现场状态与系统登记分别核对，接班人应能据原始凭证恢复未完成事项。",
        "campaign": f"活动负责人遇到{branch['situation']}时采用：{branch['decision']}。已作出的用户承诺另核原版本，未核实部分暂停新增宣传，恢复前要更新并复核对客说明。",
        "retro": f"本次复盘事件起点是{branch['condition']}。记录采用的处置为：{branch['decision']}。复盘不声称此举已改善销量或召回效果；是否结案仍需核对原始凭证。",
    }
    if version == 2:
        clause += " 模拟修订已生效：" + family["revision"] + "。"
    proof_action = {
        "supplier": "作为供方确认附件逐项回传",
        "product": "作为型号与适用范围的核对依据",
        "sop": "由执行人留存并交给复核人",
        "campaign": "在恢复宣传前由活动负责人核对",
        "retro": "按发生顺序归档以支持责任复核",
    }[kind]
    relation = (
        f"模拟供货事实：{supplier}为{store}提供{first}和{second}；这只是本场景供货联系。"
        f"本{LABELS[kind]}适用于这两个商品的{family['title']}事项。联系存在不代表允许替代，"
        "本记录没有声称列全全部下游门店；实时数量、现价、任务状态须查询业务系统。"
    )
    return [
        {
            "heading": "范围与身份",
            "text": f"模拟 {store}，{supplier}，{first}、{second}。场景：{family['title']} / {branch['situation']}。本件为{LABELS[kind]}，用途是明确本次商业决定、证据与未授权边界。",
        },
        {"heading": "角色条款", "text": "模拟：" + clause + "。"},
        {
            "heading": "适用条件与处置",
            "text": "模拟：当" + branch["condition"] + "时，" + roles[kind],
        },
        {
            "heading": "所需材料与数量口径",
            "text": "模拟：需要"
            + branch["proof"]
            + "，"
            + proof_action
            + "。未取得必要批准或材料时保持待核，不直接执行放行、替换或退款。"
            + scenario["facts"][1]["text"]
            + "该数量不是食品安全阈值或法定要求。",
        },
        {
            "heading": "例外及未确认范围",
            "text": "模拟："
            + branch["exception"]
            + "。"
            + ("真实厂商、行业和法律要求应另查可核实原始指引；这里没有生成相关阈值。"),
        },
        {"heading": "供货联系与适用范围", "text": relation},
        {
            "heading": "版本与有效期",
            "text": f"模拟版本{version}。"
            + (
                f"本修订替代{previous}的角色条款；新增要求为：{family['revision']}。历史日期仍按旧版判断。"
                if version == 2
                else "原始版本。后续修订如生效，按查询日期选择；上传先后不自动决定适用。"
            ),
        },
    ]


def _public(root):
    path = root / "public-sources.jsonl"
    if not path.exists():
        return [], [], []
    sources, records, problems = [], [], []
    for raw in read_jsonl(path):
        try:
            source = validate_source(raw)
            sources.append(source)
            if source["acquisition_status"] != "acquired":
                continue
            original = safe_path(root, source["original_path"]).read_bytes()
            if digest(original) != source["content_sha256"] or len(original) != source.get(
                "size", source.get("size_bytes")
            ):
                raise ValueError("source original byte/hash mismatch")
            record = normalize_public(source)
            check = validate_manifest(build_manifest([record], root), root)
            if check["errors"]:
                raise ValueError("ingestion representation failed byte/hash checks")
            records.append(record)
        except (ValueError, KeyError, OSError):
            problems.append(
                {
                    "source_family_id": raw.get("source_family_id"),
                    "reason": "invalid metadata or original/normalized bytes; not counted",
                }
            )
    # Same source family must not inflate independent public quota through alternate representations.
    seen_families, seen_documents, seen_hashes, unique = set(), set(), set(), []
    for record in records:
        if (
            record["source_family_id"] in seen_families
            or record["document_fixture_id"] in seen_documents
            or record["sha256"] in seen_hashes
        ):
            problems.append(
                {
                    "source_family_id": record["source_family_id"],
                    "reason": "duplicate source/document/content; not counted",
                }
            )
            continue
        unique.append(record)
        seen_families.add(record["source_family_id"])
        seen_documents.add(record["document_fixture_id"])
        seen_hashes.add(record["sha256"])
    return sources, unique, problems


def build(root=ROOT, stage="full"):
    root = Path(root).resolve()
    if stage not in {"pilot", "full"}:
        raise ValueError("stage must be pilot or full")
    ledger_path = root / "ownership.json"
    ledger = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.exists()
        else {"owner": OWNER, "files": {}}
    )
    if ledger.get("owner") != OWNER:
        raise ValueError("ownership ledger belongs to another writer")
    old_hash = digest(ledger_path.read_bytes()) if ledger_path.exists() else None
    # Preflight every existing owned file before any writes, including frozen gold.
    for relative, sha in ledger["files"].items():
        if (
            not safe_path(root, relative).is_file()
            or digest(safe_path(root, relative).read_bytes()) != sha
        ):
            raise ValueError(f"owned file modified or missing: {relative}")
    reserved = [
        "cases.jsonl",
        "queries-dev.jsonl",
        "scenarios.jsonl",
        "sources.jsonl",
        "schema.json",
        "entities-fixture.json",
        "relations.jsonl",
        "facts/evidence.jsonl",
        "freeze-evidence.json",
    ]
    for relative in reserved:
        if safe_path(root, relative).exists() and relative not in ledger["files"]:
            raise ValueError(f"ownership missing: {relative}")
    files = {}
    catalog, scenarios = families(), scenario_rows()
    active = scenarios if stage == "full" else scenarios[:30]
    records, evidence, source_rows, document_texts = [], [], [], []
    by_scenario, revision_edges = {}, []
    serial = 0
    for slot, scenario in enumerate(active):
        family = catalog[slot % 30]
        branch = family["branches"][slot // 30]
        for kind, quota in QUOTAS.items():
            count = (slot + 1) * quota // 150 - slot * quota // 150
            for ordinal in range(1, count + 1):
                document_id = f"SYN-{scenario['scenario_id']}-{kind}-{ordinal}"
                ext = FORMATS[serial % len(FORMATS)]
                revised = serial < REVISION_COUNT
                versions = [1, 2] if revised and stage == "full" else [1]
                serial += 1
                for version in versions:
                    version_id = f"{document_id}-v{version}"
                    relative = f"originals/{kind}/{version_id}.{ext}"
                    title = f"模拟 {family['title']} {branch['situation']} {LABELS[kind]} {['主件', '识别交接补充', '适用变更说明'][ordinal - 1]}"
                    sections = _sections(
                        family, branch, scenario, kind, ordinal, version, f"{document_id}-v1"
                    )
                    data, locators = render_document(title, sections, ext)
                    files[relative] = data
                    interval = dict(scenario["effective_interval"])
                    change_date = interval["from"][:8] + "16"
                    if revised:
                        interval["until" if version == 1 else "from"] = change_date
                    provenance = {
                        "source_kind": "synthetic_business_document",
                        "source_family_id": "SYN-" + family["family_id"],
                        "scenario_family_id": family["family_id"],
                        "source_url": None,
                        "publisher": "ShopSteward synthetic corpus",
                        "jurisdiction": "SIMULATED",
                        "synthetic": True,
                    }
                    metadata = {
                        "title": title,
                        "category": kind,
                        "store_fixture": scenario["store_fixture"],
                        "sku_fixture_ids": scenario["sku_fixture_ids"],
                        "supplier_fixture_ids": [scenario["supplier_fixture_id"]],
                        "entity_refs": scenario["entity_refs"],
                        "scenario_id": scenario["scenario_id"],
                        "valid_from": interval["from"] + "T00:00:00Z",
                        "valid_until": interval["until"] + "T00:00:00Z",
                        "provenance": provenance,
                        "author": "Codex assistant",
                        "generation_method": "authored scenario composition",
                        "generation_input_sha256": scenario["generation_input_sha256"],
                        "revision_number": version,
                        "supersedes": f"{document_id}-v1" if version == 2 else None,
                    }
                    record = {
                        "document_fixture_id": document_id,
                        "version_fixture_id": version_id,
                        "original_path": relative,
                        "mime": MIMES[ext],
                        "size": len(data),
                        "sha256": digest(data),
                        "source_family_id": provenance["source_family_id"],
                        "scenario_family_id": family["family_id"],
                        "metadata": metadata,
                        "synthetic": True,
                    }
                    records.append(record)
                    source_rows.append(
                        validate_source(
                            {
                                "source_family_id": provenance["source_family_id"],
                                "title": title,
                                "publisher": provenance["publisher"],
                                "url": None,
                                "language": "zh-CN",
                                "jurisdiction": "SIMULATED",
                                "publication_date": None,
                                "retrieved_at": "2026-09-07T00:00:00Z",
                                "acquisition_status": "acquired",
                                "use_terms_status": "assistant_authored_synthetic_fixture",
                                "source_kind": provenance["source_kind"],
                                "original_path": relative,
                                "content_sha256": record["sha256"],
                                "document_fixture_id": document_id,
                                "version_fixture_id": version_id,
                                "synthetic": True,
                            }
                        )
                    )
                    for i, (section, locator) in enumerate(zip(sections, locators, strict=True)):
                        evidence.append(
                            {
                                "evidence_id": f"{version_id}:E{i + 1}",
                                "source_version_id": version_id,
                                "document_fixture_id": document_id,
                                "scenario_id": scenario["scenario_id"],
                                "scenario_family_id": family["family_id"],
                                "locator": locator,
                                "quote": section["text"],
                                "original_sha256": record["sha256"],
                                "content_sha256": digest(section["text"].encode("utf-8")),
                                "synthetic": True,
                            }
                        )
                    if version == 1:
                        by_scenario.setdefault(scenario["scenario_id"], {}).setdefault(
                            kind, []
                        ).append(record)
                        document_texts.append(
                            {
                                "id": document_id,
                                "text": "\n".join(s["text"] for s in sections[1:5]),
                                "scenario_id": scenario["scenario_id"],
                                "category": kind,
                            }
                        )
                    else:
                        revision_edges.append(
                            {
                                "relation_id": f"{version_id}:supersedes",
                                "from_entity": version_id,
                                "to_entity": f"{document_id}-v1",
                                "relation_type": "SUPERSEDES",
                                "source_version_id": version_id,
                                "locator": locators[6],
                                "evidence_id": f"{version_id}:E7",
                                "conditions": [family["revision"]],
                                "effective_interval": interval,
                                "assertion_status": "synthetic_verified",
                            }
                        )
    cases, relations = [], list(revision_edges)
    for slot, scenario in enumerate(active):
        family_index = slot % 30
        branch = catalog[family_index]["branches"][slot // 30] | {"index": slot // 30}
        docs = by_scenario[scenario["scenario_id"]]
        supplier_doc, product_doc = docs["supplier"][0], docs["product"][0]
        # A single fact set is shared by relational SQL selection and bounded traversal.
        for sku in scenario["sku_fixture_ids"]:
            for relation_type, start, end, doc in [
                ("SUPPLIES", scenario["supplier_fixture_id"], sku, supplier_doc),
                ("APPLIES_TO", product_doc["version_fixture_id"], sku, product_doc),
            ]:
                relations.append(
                    {
                        "relation_id": f"{scenario['scenario_id']}:{relation_type}:{sku}",
                        "from_entity": start,
                        "to_entity": end,
                        "relation_type": relation_type,
                        "source_version_id": doc["version_fixture_id"],
                        "locator": next(
                            e["locator"]
                            for e in evidence
                            if e["evidence_id"] == doc["version_fixture_id"] + ":E6"
                        ),
                        "evidence_id": doc["version_fixture_id"] + ":E6",
                        "conditions": [
                            "only declared store, SKU, business purpose and effective interval",
                            "association does not authorize substitution or prove complete impact",
                        ],
                        "effective_interval": {
                            "from": doc["metadata"]["valid_from"][:10],
                            "until": doc["metadata"]["valid_until"][:10],
                        },
                        "assertion_status": "synthetic_verified",
                    }
                )
        as_of = scenario["effective_interval"]["from"][:8] + "10"
        plans = query_plan(
            family_index,
            branch,
            scenario["store_fixture"],
            scenario["supplier_fixture_id"],
            scenario["sku_fixture_ids"],
            as_of,
        )
        for q, plan in enumerate(plans):
            selected = supplier_doc if q == 0 else product_doc
            required = [
                [selected["version_fixture_id"] + ":E2"],
                [selected["version_fixture_id"] + ":E3"],
            ]
            if plan["group"] in {"cross_document", "hybrid"}:
                required.append([docs["sop"][0]["version_fixture_id"] + ":E2"])
            if plan["relation_tags"]:
                required += [
                    [supplier_doc["version_fixture_id"] + ":E6"],
                    [product_doc["version_fixture_id"] + ":E6"],
                ]
                if plan["relation_tags"] == ["condition_unsatisfied"]:
                    required.append([selected["version_fixture_id"] + ":E4"])
            if plan["group"] == "unanswerable":
                required = []
            tools = []
            if plan["group"] == "hybrid":
                tools = ["inventory_query"] if family_index in {24, 25, 27} else ["mission_query"]
                if family_index == 26 and q == 0:
                    tools.append("price_query")
            case = {
                "case_id": f"Q-{scenario['scenario_id']}-{q + 1}",
                **plan,
                "scenario_family_id": scenario["scenario_family_id"],
                "scenario_id": scenario["scenario_id"],
                "source_family_ids": ["SYN-" + scenario["scenario_family_id"]],
                "store_fixture": scenario["store_fixture"],
                "as_of": as_of,
                "required_evidence": required,
                "forbidden_claims": [
                    branch["exception"],
                    "不得以静态文档声称当前库存、现价或任务结果",
                    "不得把有联系当作已批准替代或全部影响范围",
                ],
                "business_tools": tools,
                "missing_conditions": ["current business response"] if tools else [],
                "expected_behavior": "abstain_and_explain_missing_evidence"
                if not required
                else "cite_required_conditions",
                "gold_status": "assistant_annotated_pending_human_review",
            }
            cases.append(validate_case(case))
    validate_case_splits(cases)
    evidence_map = {row["evidence_id"]: row for row in evidence}
    version_map = {row["version_fixture_id"]: row for row in records}
    enriched = []
    for relation in relations:
        document = version_map[relation["source_version_id"]]
        ev = evidence_map[relation["evidence_id"]]
        actual = extract_sections(
            files[document["original_path"]], Path(document["original_path"]).suffix[1:]
        )
        enriched.append(intake_metadata(relation, document, ev["quote"], actual[ev["locator"]]))
    relations = enriched
    public_sources, public_records, public_problems = _public(root)
    files.update(
        {
            "schema.json": json_bytes(SCHEMA),
            "entities-fixture.json": json_bytes(entities()),
            "scenarios.jsonl": jsonl_bytes(active),
            "sources.jsonl": jsonl_bytes(source_rows + public_sources),
            "cases.jsonl": jsonl_bytes(cases),
            "queries-dev.jsonl": jsonl_bytes(export_queries(cases)),
            "relations.jsonl": jsonl_bytes(relations),
            "facts/evidence.jsonl": jsonl_bytes(evidence),
            "facts/document-texts.jsonl": jsonl_bytes(document_texts),
        }
    )
    manifests = {}
    for name in ["pilot", "full"] if stage == "full" else ["pilot"]:
        subset = (
            records
            if name == "full"
            else [
                r
                for r in records
                if r["metadata"]["scenario_id"] in {s["scenario_id"] for s in scenarios[:30]}
                and r["metadata"]["revision_number"] == 1
            ]
        )
        target = 100 if name == "full" else 20
        # Public source order is deterministic; raw archives and companion text count once.
        public_subset = (
            public_records
            if name == "full"
            else [r for r in public_records if r["metadata"].get("acquisition_batch") == "pilot20"]
        )[:target]
        manifest = build_manifest(subset + public_subset, root)
        manifest.update(
            stage=name,
            target_logical_document_count=1000 if name == "full" else 200,
            public_target=target,
            public_acquired_count=len(public_subset),
            public_gap=max(0, target - len(public_subset)),
            quota_status="met" if len(public_subset) == target else "public_shortfall",
            public_import_issues=public_problems,
            ingestion_scope="only listed originals and metadata; no facts, cases or relations gold",
            public_adoption="background_only_no_store_policy_adoption",
        )
        manifests[name] = manifest
        files[f"manifests/{name}.json"] = json_bytes(manifest)
    demo = current_agent_subset(manifests["pilot"], cases, "2026-09-08T00:00:00+08:00")
    demo_manifest = build_manifest(demo["documents"], root)
    demo_manifest.update(
        snapshot_as_of=demo["snapshot_as_of"],
        source_manifest="pilot.json",
        quality_counts_excluded=True,
        historical_agent_evaluation=False,
        scope="only currently effective synthetic pilot documents; no redating",
    )
    files["manifests/current-agent-pilot.json"] = json_bytes(demo_manifest)
    files["current-agent-cases.jsonl"] = jsonl_bytes(demo["cases"])
    files["manifests/stress.json"] = json_bytes(
        {
            "dataset": "expanded-stress-only",
            "source_manifest": "full.json",
            "quality_denominator": False,
            "targets_chunk_count": [10000, 50000, 100000],
            "chunk_count": None,
            "status": "not_materialized_requires_actual_parser_chunks",
            "isolation": "separate indexes; clones never count toward quality documents or 300 questions",
        }
    )
    # Freeze query/fact/original identities; public additions are separately reported, never invented.
    freeze = {
        "evaluation_version": "expanded-v1.2",
        "revision_reason": (
            "Repair CSV header/metadata rectangularity only; business rows, locators, queries, "
            "dates and public data unchanged. Explicit relation intake metadata retained from v1.1."
        ),
        "stage": stage,
        "human_review": "pending",
        "retrieval_run": "not_run",
        "frozen_before_tuning": True,
        "files": {
            p: digest(data)
            for p, data in files.items()
            if p.startswith(("originals/", "facts/"))
            or p
            in {
                "cases.jsonl",
                "queries-dev.jsonl",
                "relations.jsonl",
                "scenarios.jsonl",
                "entities-fixture.json",
                "sources.jsonl",
                "schema.json",
                "manifests/full.json",
                "manifests/pilot.json",
            }
        },
        "public_originals": {r["original_path"]: r["sha256"] for r in public_records},
        "revision_policy": "Change frozen test requires a new evaluation version and written reason.",
    }
    files["freeze-evidence.json"] = json_bytes(freeze)
    # Do not silently revise frozen tests after full-stage publication.
    if (root / "freeze-evidence.json").exists():
        previous = json.loads((root / "freeze-evidence.json").read_text(encoding="utf-8"))
        validate_freeze(previous, freeze)
        if previous.get("evaluation_version") == "expanded-v1":
            files["freeze-history/expanded-v1.json"] = json_bytes(previous)
            previous_relations = read_jsonl(root / "relations.jsonl")
            current_relations = {r["relation_id"]: r for r in relations}
            if len(previous_relations) != len(current_relations) or any(
                {key: current_relations.get(old["relation_id"], {}).get(key) for key in old} != old
                for old in previous_relations
            ):
                raise ValueError("relation annotation upgrade must preserve semantic facts")
            files["freeze-history/expanded-v1-relations.jsonl"] = (
                root / "relations.jsonl"
            ).read_bytes()
        if previous.get("evaluation_version") == "expanded-v1.1":
            files["freeze-history/expanded-v1.1.json"] = json_bytes(previous)
            changes = []
            for relative in list(files):
                if not (relative.startswith("originals/") and relative.endswith(".csv")):
                    continue
                old_data = (root / relative).read_bytes()
                old_rows = list(csv.reader(io.StringIO(old_data.decode("utf-8-sig"))))
                new_rows = list(csv.reader(io.StringIO(files[relative].decode("utf-8-sig"))))
                if (
                    new_rows[0] != old_rows[1]
                    or new_rows[1] != ["metadata", *old_rows[0]]
                    or new_rows[2:] != old_rows[2:]
                ):
                    raise ValueError(
                        "CSV format repair must preserve every business row and locator"
                    )
                files["freeze-history/expanded-v1.1/" + relative] = old_data
                changes.append(
                    {
                        "path": relative,
                        "previous_sha256": digest(old_data),
                        "sha256": digest(files[relative]),
                        "byte_delta": len(files[relative]) - len(old_data),
                        "business_rows_unchanged": True,
                        "locators_unchanged": True,
                    }
                )
            for relative in ("manifests/full.json", "manifests/pilot.json"):
                files["freeze-history/expanded-v1.1/" + relative] = (root / relative).read_bytes()
            files["reports/csv-v1.2-repair.json"] = json_bytes(
                {
                    "previous_evaluation_version": "expanded-v1.1",
                    "evaluation_version": "expanded-v1.2",
                    "reason": freeze["revision_reason"],
                    "changed_original_count": len(changes),
                    "changes": changes,
                    "non_csv_originals_unchanged": True,
                    "cases_sha256_unchanged": previous["files"]["cases.jsonl"]
                    == digest(files["cases.jsonl"]),
                }
            )
    # Preflight all destinations before modifying any, including newly added originals.
    for relative in files:
        if safe_path(root, relative).exists() and relative not in ledger["files"]:
            raise ValueError(f"ownership missing: {relative}")
    for relative, data in files.items():
        if ledger["files"].get(relative) == digest(data):
            continue
        ledger["files"][relative] = write_owned(root, relative, data, ledger["files"].get(relative))
    write_owned(root, "ownership.json", json_bytes(ledger), old_hash)
    return manifests[stage]
