# Expanded corpus quality report

2026-09-08, release expanded-v1.2. Scope: A1 and the local synthetic A2/A3 deliverables, with the independent public
agent's actual files aggregated. Public100, human review, stress materialization, normal API
ingestion, live retrieval and cloud evaluation are not claimed complete.

## Actual inventory

| Category | Pilot logical documents | Full logical documents |
|---|---:|---:|
| Synthetic supplier terms | 36 | 180 |
| Synthetic product/packaging | 64 | 320 |
| Synthetic SOP | 32 | 160 |
| Synthetic campaign | 20 | 100 |
| Synthetic retrospective | 28 | 140 |
| Acquired public sources | 20 | 24 |
| Total | **200** | **924** |

The full manifest has **1,124 version records**: 924 logical documents and 200 additional
synthetic revisions. The target of 1,000 logical documents remains **76 public documents
short**. Public pilot selection explicitly uses `acquisition_batch=pilot20`.

| Bytes represented | Exact bytes |
|---|---:|
| Full synthetic base originals | 8,763,728 |
| Separate synthetic revisions | 1,966,213 |
| Full public normalized ingestion texts | 941,572 |
| Full ingestion manifest total | **11,671,513** |
| Pilot ingestion manifest total | **2,432,944** |
| Public raw PDF/HTML provenance, separate from ingestion text | 12,684,550 |

Raw public originals and normalized companions are two representations of the same sources,
not extra logical documents. Raw archives and normalized text hashes are both checked.

Full format counts, including revisions: MD 208, TXT 184, CSV 183, PDF 183, DOCX 183,
XLSX 183. Synthetic base originals have 150 of each format; the 24 public ingestion documents
are normalized MD. Pilot has MD 50 and 30 each of the other five formats.

Full independent lineage counts: 30 synthetic scenario families plus 24 public source families
= **54 source families**. Pilot: 30 + 20 = **50**. Source families are not equated with distinct
publishers or independent real companies. Manifest `chunk_count` remains null to preserve
the frozen ingestion inputs; the separate final local parser report records 16,205 chunks.

## Substance, diversity and review

The authored catalog contains 30 families and 150 situation branches. Five branches in a family
change prerequisites, actions, required evidence or the exception that blocks the action.
Examples include early-arrival versus blocked-entrance unloading; outer-box damage versus
missing dispute goods; cup-lid lock mismatch versus missing model coverage; unapproved coupon
stacking versus refund recalculation; and incomplete recall/transfer chains versus explicit
batch scope. The same underlying scenario is written for different operational roles, each
with its own procurement, product, operations, promotion or retrospective decision.

Additional same-category documents have separate purposes: dispute settlement, product identity
and handover, recovery and shift handover, or scope-change approval. Entity numbers and dates
are fixtures; those substitutions do not constitute the intended business novelty. The four
core business sections contain 250–360 Chinese characters per base document (median 279),
excluding identity, relationship, version and layout boilerplate. These are concise operating
documents, not long manuals.

Initial assistant content spot-check: 20 base documents, comprising all five categories in
F03 (split delivery), F06 (minimum-order combinations), F09 (barcode migration) and F12
(return packaging), branch B1. The reviewed role clauses distinguish actual receipt from
in-transit quantities, eligible order rows from gifts/returns, sales barcodes from warehouse
codes, and approved return packaging from merely similar packaging. Their source/evidence
locations were then validated against actual originals.

All 900 base documents and 200 revisions passed deterministic byte, reference, entity, temporal
and evidence checks. This is broader mechanical coverage, **not a claim of independent editorial
review of every document or every 20-document batch**. Full independent editorial review remains
pending. The template structure and repeated operational cautions are deliberately disclosed.

Exact duplicate byte groups: **0**. Synthetic base-original near-duplicate candidates at
stripped character 5-gram Jaccard >= 0.85: **0**. Normalization removes IDs, numbers and frequent
whole-sentence boilerplate; revisions are intentionally excluded from the near-duplicate
quality denominator. This threshold is an alert heuristic, not a proof of semantic originality.
Public near-duplicate research is the source agent's separate responsibility; this audit checks
their acquired hashes, source-family uniqueness and representations without fabricating quota.

All six formats were round-trip checked. Every one of the 7,700 synthetic evidence records
resolves to its quoted text at a real section, paragraph, PDF page, CSV row or XLSX cell.
A seven-page PDF sample was rendered and visually inspected for Chinese glyphs and clipping.
PDF pages use one section per page for unambiguous location; these intentionally sparse layouts
are parser fixtures. Full visual inspection of every PDF/Office page is **not performed**.
Office artifacts were validated by extraction and deterministic byte checks, not a claim of
complete Word/Excel layout review. No new OCR or cached-formula challenge files were introduced.

## Evaluation and relations

Exactly **300 questions**: 40 exact/metadata, 40 keyword, 60 semantic, 60 cross-document,
40 unanswerable/conflict and 60 live-business mixed. Dev contains 100 questions from ten whole
families; test contains 200 from the other twenty. All five branches and both query intentions
of a family stay in one split. Source-family leakage is also rejected.

Sixty relation-tagged questions are a cross-label inside the 300: 12 single-step, 24 multi-step,
12 condition-unsatisfied, 12 incomplete-graph. The shared fact file contains 600 sourced
`SUPPLIES`/`APPLIES_TO` edges and 200 `SUPERSEDES` edges. Each uses `synthetic_verified`, a real
source-version locator, effective interval and explicit scope conditions. This is not a real
company verification claim, unrestricted substitution graph or exhaustive supply-chain model.

Query intentions are authored separately from documents and evidence binding. The query
planner does not read gold text, evidence locators or expected paths. Gold is synthetic-only;
the 24 public sources currently supply background corpus diversity, **not independently
annotated public-source evaluation questions**. This limits conclusions about public knowledge
retrieval. The 300 are not 300 independent human-authored intents: there are 60 authored query
intentions applied to 150 substantively different branches, grouped and split conservatively.

All evidence is verified against query store and as-of date. Queries use the tenth day of each
scenario's month; revisions take effect on the sixteenth. Historical-v1 retrieval is therefore
required despite later-uploaded v2. Pilot-only construction declares the same planned boundary
as the full set. Additional after-revision question coverage would require a new frozen version.

Required-evidence scoring uses a separate denominator for every necessary condition, allowing
alternative IDs per condition. Missing result rows are zero rather than silently omitted;
unanswerable questions return null evidence recall and separately track explicit abstention.
Empty actual-result files cannot produce effectiveness scores. No actual retrieval result file
was supplied or manufactured here: **all lexical/dense/hybrid/model scores remain unrun**.

## Reproducibility and boundaries

Two fresh isolated full builds produced identical generated hashes. The verifier also compares
the rebuilt manifest to the manifest under audit. External files were unchanged, including all
**91 K0 files**; hashes are saved in `reports/k0-preservation.json`. No K0, IH, dependency, root
configuration or environment file was edited. No commit was created.

Ownership writes require the previous hash and reject traversal, untracked existing files,
manual modifications and missing owned files. Full freeze includes originals, sources,
manifests, schema, scenarios, entities, relations and evaluation facts/queries. Frozen content
or public-snapshot changes require a new evaluation version/root and a written explanation;
the builder refuses silently overwriting them.

The stress manifest only declares separate 10k/50k/100k chunk targets and explicitly reports
`not_materialized_requires_actual_parser_chunks`. Stress clones are absent from quality counts
and question denominators. Live business calls, K1 upload, Docker services and cloud/model
checks belong to the integration work; this corpus task does not invent their results.

Machine-readable evidence is in `reports/pilot-verification.json`,
`reports/full-verification.json`, `reports/evaluation-verification.json`, and
`reports/near-duplicates.json`. `schema-example.json` includes an actual raw manifest record,
the explicit importer adaptation and actual entity examples.

## Integration corrections and current-date scope

Release v1.1 adds explicit scalar machine conditions and exact-source quotes to all 800
relations, preserving their semantic facts. Declared `HAS_APPLICABLE_DOCUMENT` discovery
edges support SKU → document lookup without reversing the business assertion. Every fixture
remains unconfirmed/unexecutable until actual parser chunk binding; false or missing required
conditions must never become unconditional. `relation-intake-example.json` and the README
describe the PG adaptation boundary. The 300-question file is unchanged from v1.

Release v1.2 repairs the accidental CSV metadata/header shape. Actual service-parser checks
of all 183 repaired CSV versions return **183 COMPLETE, zero warnings**. Every business row
and locator is preserved; only CSV originals and their byte/hash references changed. Archived
prior originals/manifests and the per-file repair report provide the actual diff evidence.
The controller's earlier full parse (11.912 seconds, 16,205 chunks, 941 COMPLETE / 183 PARTIAL,
1,464 CSV_RAGGED_ROW warnings) applies to old manifest `08a492da9854b16bd0d488ed0bdd75982d70f3af48436fa6a2ad7282f87bb9c6`.
It must not be attributed to the repaired manifest. The controller's completed final rerun is
recorded in `var/precloud/parse-profile-final.json` (repository-relative): all **1,124 COMPLETE**,
**16,205 chunks**, **1,878,743 characters**, **18.710 s wall / 18.219 s CPU**, and Windows peak
working set **123,805,696 bytes**. Memory covers the whole parser process only, excluding
database, index and worker containers. Every report row was matched to the final manifest's
version ID/hash and the chunk/character totals were checked. No generator or manifest change
was needed. `var/precloud/relation-binding.json` records **800/800** offline quote bindings,
zero failures and zero imports; the controller used worker chunk profile `lexical-v1`.
Binding does not grant business permission or establish a successful live import.

Frozen as-of queries are historical service benchmarks. On September 8, pilot synthetic base
documents comprise 132 expired / 12 current / 36 future, and full bases comprise 606 expired /
78 current / 216 future. No dates were shifted. The separate `current-agent-pilot.json` manifest
contains 12 current originals and `current-agent-cases.jsonl` has four explicitly derived
current-date probes, excluded from the quality document count and 300-question denominator.
No historical Agent capability or successful live Agent run is inferred from these fixtures.

## Finalization and dev request handoff

The final full rebuild retains **924 logical documents / 1,124 versions**, including 900
synthetic base documents, 200 separate revisions and 24 acquired public sources. Pilot retains
**200 logical documents / 200 versions** (180 synthetic + 20 public). The public gap is still
**76**; the 1,000-document target is not met. All originals and both ingestion manifests are
byte-identical to the repaired v1.2 artifacts present at the start of this finalization.

`queries-dev.jsonl` is now generated deterministically from the 100 frozen dev cases, sorted
by case ID. Each row explicitly declares `split: dev` and contains only request fields:
case ID, query, store fixture, as-of date, entry entities and a scalar whitelist of authored
query constraints. Test cases, evidence labels, answers, expected paths and arbitrary nested
metadata are excluded. The current benchmark loader accepts all 100 requests and projects
query/as-of/store/entry entities; it does not forward the extra query-constraint dictionary.
The request file is added to the existing freeze without changing any of the 300 questions,
800 relations or four current-agent probes.

Fresh checks: 45 corpus/import tests passed; scoped Ruff checks passed; both isolated full
builds were identical and matched the real manifest. Evaluation verification resolved all
7,700 evidence records and 800 relation rows. All 183 CSV versions are rectangular and retain
their archived business rows and locators. All 1,124 manifest records passed the real upload
preparation function; all 24 public records select the normalized bytes while retaining raw
archive provenance. These are local input/integrity checks, with zero HTTP benchmark or
ingestion calls. All 91 K0 files and all preexisting public files were preserved.

SHA-256:

| Artifact | Hash |
|---|---|
| `manifests/full.json` | `34b717e436b8613d2d1624f1e6fc36ae3c38dc280dcdc28e61408c437587b0fd` |
| `manifests/pilot.json` | `28ea82fac8c315a57b38a638f6c4068260dd0db54682dc387097b5fc704f8428` |
| `queries-dev.jsonl` | `fe43c98c26c7805e5a1866dbf77e0530723d4d5320e74c78f9f854397e4b3723` |

Repeat from the repository root in PowerShell:

```powershell
& ./.venv/Scripts/python.exe backend/tools/build_knowledge_expanded_corpus.py --stage full --verify-only
& ./.venv/Scripts/python.exe backend/tools/build_knowledge_expanded_corpus.py --stage pilot --verify-only
& ./.venv/Scripts/python.exe backend/tools/verify_knowledge_expanded_corpus.py --manifest docs/evaluation/knowledge-expanded/manifests/full.json --check-reproducible
& ./.venv/Scripts/python.exe backend/tools/verify_knowledge_expanded_eval.py
& ./.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/unit/test_knowledge_corpus_expanded.py backend/tests/unit/test_knowledge_corpus_import.py -q
```

Current checks, preservation hashes and the exact changed-file list are recorded in
`reports/finalization.json`. The full parser profile remains separately owned; this handoff
references its verified report without changing its inputs. `cloud-experiment.json` now pins
`manifests/pilot.json` and `queries-dev.jsonl` to the SHA-256 values above, with status
`not_run`, billing disabled and cloud quality/latency/cost still `not_run`. No retrieval,
Agent or cloud execution is inferred from the local parsing and binding reports.
