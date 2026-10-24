# Expanded knowledge corpus

Local precloud data, release `expanded-v1.2` (questions unchanged from v1). This directory is separate from the
immutable K0 corpus in `../knowledge/`. It contains real uploadable files, not links counted as
documents. No cloud, model-quality, or successful API ingestion claim is made here.

| Manifest | Synthetic logical documents | Public logical documents | Extra revisions | Public gap |
|---|---:|---:|---:|---:|
| `manifests/pilot.json` | 180 | 20 | 0 | 0 |
| `manifests/full.json` | 900 | 24 | 200 | 76 |

Full synthetic category counts: supplier 180, product 320, SOP 160, campaign 100, retrospective
140. Pilot: 36 / 64 / 32 / 20 / 28. Thirty authored scenario families each have five distinct
business branches. The pilot contains the first branch of every family. Eight simulated stores,
40 suppliers, 300 SKUs and twelve calendar months are fixtures, never production identifiers.

## Upload boundary

Resolve every `original_path` against this directory. A manifest document has:

```text
document_fixture_id, version_fixture_id, original_path, mime, size, sha256,
source_family_id, scenario_family_id, synthetic, metadata
```

`size` means bytes. Count distinct document IDs as logical documents; `version_count` includes
base versions and revisions. `source_family_count` counts source/scenario lineage, not PDFs,
chapters, publishers or versions. `chunk_count` remains null until an actual parser supplies it.

Metadata contains `title`, `category`, `store_fixture`, `sku_fixture_ids`,
`supplier_fixture_ids`, `entity_refs`, `valid_from`, `valid_until`, and `provenance`, plus local
authoring/version information. The `provenance` object contains **only** these accepted fields:

```text
source_kind, source_family_id, scenario_family_id, source_url,
publisher, jurisdiction, synthetic
```

This seven-field object matches the current
`shopsteward_knowledge.contracts.Provenance` whitelist. Before normal K1 upload, map fixture
store/SKU/supplier IDs to actual IDs in an explicitly separate test tenant, then construct
`UploadMetadata` using only title/category/sku_ids/supplier_ids/visibility/validity/provenance.
Do not pass the entire corpus metadata dictionary into the strict API model.

`entities-fixture.json` has `stores`, `suppliers`, and `skus` arrays. All rows contain
`fixture_id`, `name`, `synthetic: true`. Each SKU additionally declares `supplier_fixture_id`
and `store_fixture_ids`. `schema-example.json` contains actual manifest and entity samples.

Revisions use the same logical ID and a new version ID. The first 200 synthetic documents
have a mid-month change with contiguous half-open validity intervals in the full manifest.
Pilot originals are the same bytes; their full-stage metadata reflects the scheduled revision.
The evaluation queries use the tenth day of the month and therefore require v1, even when v2
was uploaded later. Import order must not replace as-of version selection.

## Public sources

The independent source agent owns `public/` and `public-sources.jsonl`. The builder reads them
without modification. Raw records accept `size_bytes`, `source_url`, and nullable publication
dates. Only acquired originals with verified bytes and hashes can enter the aggregate.
Reference cards, missing files, invalid rows and duplicate source families do not meet quotas.

For records with normalized text companions, manifest `original_path`/`sha256`/`size`/`mime`
refer to `normalized_path`/`normalized_sha256`/`normalized_size_bytes`/`normalized_mime`.
Raw PDF or HTML provenance remains in `metadata.source_original_path` and
`metadata.source_original_sha256`, and complete acquisition/license records remain in sources.
This is an explicitly identified archival transformation. Pilot selection requires
`acquisition_batch=pilot20`; full includes the 24 actually acquired independent documents.
Public sources are background guidance without an asserted store-adoption relationship.

## Evaluation boundary

`cases.jsonl`, `scenarios.jsonl`, `facts/`, and `freeze-evidence.json` are offline evaluation
assets, never ingestion inputs. `relations.jsonl` is a separate source-backed fact set for SQL
selection and bounded traversal comparisons; do not indiscriminately upload the directory.
In particular, `facts/document-texts.jsonl` is duplicate-review material, not a second original.

The 300 questions have exactly 40 exact/metadata, 40 keyword, 60 semantic, 60 cross-document,
40 unanswerable and 60 live-business mixed cases. Ten whole families form 100 dev questions;
twenty other families form 200 test questions. Sixty questions have relation cross-labels;
they do not enlarge the denominator. Query intentions live in `questions.py`, which receives
only situation, entities, date and user constraints, never gold locators or expected paths.

Required evidence is a list of alternative-ID sets. Every set is one necessary condition;
retrieving any member satisfies that condition. Evidence IDs point through `facts/evidence.jsonl`
to verified original version hashes and actual section/paragraph/page/row/cell locators.
These are **not** production chunk IDs. Map retrieved original/locator references to these
offline IDs after retrieval. No evidence IDs, quotes or answer keys should be sent to search.

Relations distinguish `SUPPLIES`, `APPLIES_TO` and `SUPERSEDES`. All 800 edges are
`synthetic_verified`, with source version, locator, conditions and effective interval.
Neither reachability nor the absence of a graph edge proves substitution permission or a
complete impact scope. Relation labels cover single-step, multi-step, missing conditions and
incomplete graphs. More expressive compatibility and real adoption edges are not asserted.

## Relation intake metadata

`relations.jsonl` includes `machine_conditions`, `evidence_quote`, `retrieval_orientation`,
`retrieval_edges`, `executable: false`, and empty `evidence_chunk_ids`. These are fixture
annotations, not registered PG edges. `relation-intake-example.json` shows an actual row.

Conditions are the explicit scalar equality conjunction
`{"store_fixture": "STORE01", "scenario_id": "F01-B1", "proof_available": true}` with
the appropriate declared fixture IDs per relation. Every key must be supplied and equal;
missing keys, false proof state, empty dictionaries, unsupported values and bool/int coercion
fail closed in `machine_conditions_satisfied`. Values are requirements, not observed facts.
Never copy required `proof_available: true` into a query as proof that evidence exists.
Use caller-established state; condition-unsatisfied cases explicitly pass false. If fixture
IDs are mapped in conditions, map query context consistently as well.

Canonical `APPLIES_TO` remains document-version → SKU. Its declared discovery edge is
SKU → document-version with predicate **`HAS_APPLICABLE_DOCUMENT`**, orientation
`declared_reverse_lookup_not_business_inverse`. Supplier → SKU → document lookup uses
`SUPPLIES` then `HAS_APPLICABLE_DOCUMENT`; it does not assert inverse business permission.
`SUPERSEDES` and `SUPPLIES` use their declared forward orientation. Explicitly add the
discovery predicate to the retrieval allowlist; never reverse arbitrary relations.

`evidence_quote` is an exact substring of the actual extracted source section, retaining PDF
layout whitespace. It is not a chunk ID. For PG intake, map fixture subjects/objects/version
IDs, bind the quote to actual parser evidence from the same original hash/version, obtain
real chunk IDs and published generation/metadata revision, then register the selected
retrieval edge. Until this succeeds, keep it unregistered: status
`requires_actual_parser_quote_binding`, `confirmed=false`, no fabricated IDs. Unresolved
quotes are `not_executable_quote_unresolved` and have no retrieval edges. Any later API
`confirmed=true` represents an evidenced synthetic fact, not real business permission.

## Current Agent demonstration and historical evaluation

The 300 frozen questions are historical as-of service evaluation, not a current-only Agent
test. At 2026-09-08, the pilot's 180 synthetic originals comprise 132 expired, 12 effective and
36 future documents. The full base set has 606 expired, 78 effective and 216 future originals.

`manifests/current-agent-pilot.json` snapshots the 12 effective synthetic pilot documents at
`2026-09-08T00:00:00+08:00`. It reuses their IDs/bytes/dates and adds nothing to quality counts.
`current-agent-cases.jsonl` has four derived live-demo queries: two evidence questions and two
document-only no-answer probes, from F09 and F21. Each records `source_case_id`, `source_as_of`,
the new explicit demo date, and `quality_evaluation_member=false`. They do not replace any of
the 300 frozen questions. Real business responses need separate verification; no live run is
claimed here. This dated snapshot is not rolling-current: `current_agent_subset` accepts a
new explicit timezone-aware instant to form another subset without shifting document dates.

## Release history

v1.1 added relation intake annotations and the separate Agent snapshot while preserving
queries, original bytes and semantic relations. v1.2 repairs CSV serialization: a real
three-column header, a rectangular metadata row, and unchanged business rows beginning at
row 3. Exactly 183 CSV versions changed, adding 9 bytes each. Non-CSV originals, business
text/locators, dates and questions are unchanged. Previous CSVs/manifests and freeze records
are preserved under `freeze-history/`; they are not extra ingestion/quality documents.
See `reports/csv-v1.2-repair.json` for exact before/after hashes.

An already uploaded CSV version must remain immutable in K1. Use a fresh isolated import run
for this corpus release, or append through the normal version API; never overwrite an earlier
stored original in place. Reproducibility checks protect every preexisting file and report
new public-acquisition files separately from modifications by the verifier.

## Commands

Run from the repository root with its existing virtual environment. Office/PDF authoring uses
the bundled document runtime, automatically located under the current user's runtime cache;
`KNOWLEDGE_DOCUMENT_PYTHON` may point at that existing executable. No dependency installation
is performed.

```powershell
& ./.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/unit/test_knowledge_corpus_expanded.py -q
& ./.venv/Scripts/python.exe backend/tools/build_knowledge_expanded_corpus.py --stage full
& ./.venv/Scripts/python.exe backend/tools/build_knowledge_expanded_corpus.py --stage pilot --verify-only
& ./.venv/Scripts/python.exe backend/tools/verify_knowledge_expanded_corpus.py --manifest docs/evaluation/knowledge-expanded/manifests/full.json --check-reproducible
& ./.venv/Scripts/python.exe backend/tools/verify_knowledge_expanded_eval.py
```

The builder can use `--root <empty-directory>` for isolation. Rebuilding full is deterministic.
After a full freeze, downgrade to pilot or changed frozen originals/questions/facts/public
snapshots is refused. Use a new evaluation root/version and record a reason for intentional
changes. Do not hand-edit generated originals or the ownership ledger to bypass the freeze.

The verify-only command is read-only. Integrity success (exit 0) does not mean the public100
quota is met; inspect `public_gap` and `quota_status`. The reproducibility verifier creates two
fresh isolated builds and compares generated hashes while checking external and K0 files.

For actual offline scoring, supply `--results path/to/results.jsonl`. Each row contains
`case_id`, `retrieved_evidence: [offline evidence IDs]`, and optionally `abstained: true`.
Missing result rows count as zero for answerable questions, not removed cases. Unanswerable
cases are excluded from evidence recall and separately report explicit abstention. An empty
result file cannot produce a score. This scorer checks evidence coverage, not answer truth,
latency or the correctness of live business-tool outputs.

## Quality limits

See `quality-report.md` and `reports/`. Synthetic documents use deliberately simple layouts and
shared document structure. Business conditions and role-specific decisions are authored;
numeric/entity changes are not accepted as sufficient novelty. Hash checks plus stripped
character 5-gram Jaccard at 0.85 are duplicate alerts, not proof of universal originality.
Questions, relation facts and gold are assistant-authored; no independent human review has
occurred. Public sources are not gold-bearing evaluation cases. The set demonstrates local
fixture integrity, not real customer usefulness or vector-search gains.

`manifests/stress.json` names isolated 10k/50k/100k chunk targets. It explicitly records that
stress materialization and actual chunk counts await parser output; no clones enter the
quality count or the 300-question denominator. OCR/scanning/formula anomalies remain K0
regressions rather than artificially multiplying expanded documents.
