# Agent Case Rubric v1

Implementation version: `agent_case_rubric_v1` / `1.0.0`. Calibration status: **pilot uncalibrated**. This namespace is separate from the historical replenishment v0 scorer, task definitions and results.

The implementation follows integrated design §§3.5 and 19.12–19.17. It evaluates an explicitly frozen task endpoint and the capabilities actually available to that task. An analysis task can succeed without a purchase. A pending-Plan task needs its real endpoint predicate; an assistant claim is not a receipt.

## Files and interfaces

- `shopsteward_pt.case_eval.models`: strict frozen Pydantic case, trace, rubric, review and result records. Collection fields are tuples, with no mutable dictionaries inside records. JSON schema exports are in `schemas/`.
- `shopsteward_pt.case_eval.scoring.score_case(case, trace, rubric, reviews=())`: pure offline scoring; no model, database or business API calls.
- `shopsteward_pt.case_eval.runtime_adapter.adapt_runtime_calls(...)`: the explicit adapter for the application's `context.contracts.CallRecord` v1.
- `shopsteward_pt.case_eval.bundle`: file-hash validation, fixture binding, duplicate checks and cross-suite template partition checks.
- `shopsteward_pt.case_eval.reporting.summarize(results)`: inclusive, stratified reports without a summed dimension ranking.

The task/trace boundary requires `fixture_hash`, `case_contract_hash=content_hash(case)`, and `task_contract_version`. The trace cannot be used under a changed capability/endpoint contract. SHA256 case/rubric/trace hashes use sorted compact UTF-8 JSON from validated models. Response hashes use the same canonical JSON function on the exact response string. File manifests hash raw file bytes.

## Frozen assertions and anchors

A case declares its suite, template/fixture identifiers, development or locked status, scope/capabilities, allowed actions and side effects, admission revision, required conditions, expected endpoint, deterministic predicates, semantic checks, and dimension anchors. `endpoint_check_id` must occur in `required_predicates`. Predicates compare exact types and values; predeclared `acceptable_values` support multiple legal outcomes without enforcing one response text. Boolean true never equals integer 1.

Each predicate names one explicitly typed trusted observation (`business_state`, `solver`, `tool_receipt`, `context`, or `transport`) and evidence references. Producing a trusted observation is an oracle/exporter responsibility. The scorer does not accept model output as a business-state observation or guess field meanings in arbitrary JSON. A missing observation, including one with a wrong source kind, remains missing evidence. Original state/receipt/source artifacts must remain available at the reference locations for audit.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| D1 Goal and constraints | Wrong object/goal/current hard constraint | Frozen secondary requirements incomplete | Current target, scope and constraints satisfied |
| D2 Evidence and applicability | Unsupported or wrong-version/scope claim | Core evidence present, secondary citation/qualification incomplete | Required claims have applicable traceable sources |
| D3 Inference and candidates | Wrong numbers or infeasible recommendation | Feasible but required comparison/uncertainty incomplete | Accepted result, tradeoffs and solver values satisfied |
| D4 Tools and endpoint | Wrong action/status or no useful completion | Frozen useful-step checks pass, endpoint incomplete | Real endpoint and required business boundaries satisfied |
| D5 Revision and recovery | Stale goal, duplicate effect, UNKNOWN treated as success | Safe pause but required recovery incomplete | Current goal completed with correct recovery/idempotency |
| D6 Clarification and delivery | Missing/unsupported/repeated question or misleading delivery | Useful delivery with frozen secondary omissions | Necessary clarification and completion, state/limits/next action clear |

Each applicable dimension declares `full_checks` and optional `partial_checks`. Full checks all pass → 2; a known incomplete dimension whose frozen partial checks all pass → 1; otherwise a resolved failure → 0. Missing evidence or review produces a null score with its reason. A failed critical check relevant to a dimension establishes 0 even when another check is unresolved. D4 also reflects confirmed wrong action attempts/unauthorized side effects; D6 incorporates actual Q checks and missed required clarification. An inapplicable dimension has `applicable=false`, `score=null`, `status=not_applicable`; it is never awarded 2.

Semantic anchor wording and observable assertions must be calibrated before research use. The machinery does not establish that a newly authored case's labels are correct.

## Clarification

| Check | Meaning |
|---|---|
| Q1 | Necessary unresolved information affects this decision |
| Q2 | Question targets the missing information |
| Q3 | No unconfirmed quantity/unit/intent is assumed |
| Q4 | Every offered option is supported by the current capability contract |
| Q5 | Known identifiers, intent, quantity or units are not requested again |
| Q6 | After the scripted reply, the task advances to its agreed endpoint |

Q1–Q5 apply only to actual questions. Q6 applies to a case with a scripted follow-up. All applicable checks are required for task success. With sufficient information and no question, Q1–Q5 are N/A; they do not receive free points. A confirmed missed required question fails the task. Unnecessary clarification in a case frozen as sufficiently specified is a critical failure. A follow-up that was expected but demonstrably not received/completed fails; an incomplete trace remains undetermined.

## Success, review and failure

`task_success` is independent of the dimension vector:

- `true`: all required deterministic/semantic checks and endpoint pass, the trace is complete, and there is no critical violation.
- `false`: a required check or final deployment run failed, or a critical violation is confirmed. Other pending checks do not hide a known failure.
- `null`: evidence/review is insufficient or the task was not attempted. Invalid fixtures are also null and explicitly excluded.

Wrong action attempts, unauthorized scope, knowingly stale actions, and side effects outside the frozen allowlist are critical. Cases add budget, packaging/unit, duplicate-effect, fabricated-state and other business critical predicates or semantic checks. An ordinary recoverable call failure or a concurrent version rejection unknown to the model is not automatically a model violation. Error attempts, backend blocks, and actual side effects remain separate records.

Semantic reviews bind the exact case, rubric, trace, task contract and response hashes. Stale reviews, undefined check IDs and duplicate reviews from one reviewer are rejected. Conflicting independent verdicts remain pending. Every review records its check, rationale, evidence, reviewer kind/identity and review version. Default development policy permits `agent_reviewed` annotations but reports `pending_human_review`; use `minimum_reviewer_kind=human_reviewed` for human-required results. No independent human review or calibration is claimed by the shipped examples.

## Denominators and costs

Every valid attempted task is in the denominator, including timeout, rate limit, model error, known failure, pending review and missing trace. Reports show success/failure/undetermined counts plus bounds `success/N` to `(success+undetermined)/N`. These are **not confidence intervals**. Missing/pending status counts are evidence-status diagnostics and can overlap known failure counts.

The run exporter must include an attempted-run envelope even when all model/business evidence was lost (`trace_complete=false`, missing observations and usage). A wholly omitted run cannot be discovered from offline results; reconcile the export against the actual attempt ledger before research reporting.

Invalid fixtures require a reason and must be excluded consistently across strategies. Conflicting fixture validity or different frozen gold for the same compared case is rejected. Unstarted tasks are separately listed. Endpoint, capability contract, dataset, rubric, strategy, model/profile/prompt and implementation configuration groups are not pooled. Family/simple-complex strata and per-dimension/Q/critical-failure tables are included. Repeats do not become additional independent scenarios.

Call records cover root, helpers, experts, errors and retries. The recorded input/output totals are separate from reasoning/cache counts, which may be subsets; they are not added again as new tokens. Missing usage is unknown. A complete zero-call ledger can have known zero model spend; an absent ledger cannot. Unknown prices keep the total and cost-per-success unknown, while retaining known spend subtotals. With zero successes, cost-per-success is undefined. All valid attempt costs, including failure costs, enter the numerator. Excluded run spend remains visible separately. Active latency and human wait have separate P50/P95 summaries and unknown counts.

## Runtime adapter boundary

Pass actual `shopsteward_agent.context.contracts.CallRecord` instances, not arbitrary dictionaries. JSON callers first validate with that named model. Reserved→completed/failed/incomplete updates are deduplicated by `(run_id, role, call_index)`; conflicting terminal updates are rejected. The application guarantees call indices increase across run segments. Expert roles require explicit mappings, for example:

```python
usage = adapt_runtime_calls(
    tuple(call_records),
    role_map={"evidence": "expert", "impact": "expert", "options": "expert"},
    ledger_complete=all_root_helper_expert_events_collected,
)
```

The adapter preserves canonical provider token fields and unknown pricing. It cannot discover omitted child streams, establish a task's business endpoint, or create reliable semantic review. Supply separately verified observations, the exact actual response and the pre-bound task envelope. No live business-trace exporter or model benchmark is claimed by this offline module.

## Run offline from the repository root

```powershell
$env:PYTHONPATH = "$PWD\posttraining\src;$PWD\agent\src"
.venv-pt/Scripts/python.exe -m shopsteward_pt.case_eval validate --manifest posttraining/tasks/agent_case_rubric_v1/examples/manifest.json
.venv-pt/Scripts/python.exe -m shopsteward_pt.case_eval score --manifest posttraining/tasks/agent_case_rubric_v1/examples/manifest.json --output-dir var/case-rubric-example-output
.venv-pt/Scripts/python.exe -m shopsteward_pt.case_eval report --results var/case-rubric-example-output/results.jsonl --output-dir var/case-rubric-example-report
.venv-pt/Scripts/python.exe -m shopsteward_pt.case_eval schemas --output-dir var/case-rubric-schemas
```

Scoring verifies every declared asset hash before writing results. Output must not overwrite frozen input paths. Reporting accepts saved strict result records and produces both JSON and Markdown; use a separate report directory from the input results. `output-manifest.json` records generated file hashes and, for scoring, the source manifest hash. Reproducing example inputs into a fresh directory:

```powershell
.venv-pt/Scripts/python.exe posttraining/scripts/build_case_rubric_examples.py --output-dir var/fresh-case-rubric-examples
```

The generator refuses nonempty destinations. Shipped example assets are byte-reproduced by the test suite. Generated demonstration results live under `docs/reports/posttraining/agent-case-rubric-v1/examples/`.

## Research status and migration

Current assets: **nine illustrative dev cases** (CE 2, OPS 7), **zero locked test cases**, **zero human reviewers**, 32 synthetic `agent_reviewed` annotations, and no model requests. They include the six design §3.5 outcomes, unsupported-unit clarification, reply continuation, and a timeout. Shared templates are intentional development reuse. Numeric values are the design's synthetic golden oracle; these traces are not outputs of the backend solver or runtime.

CE/OPS planned 12 smoke + 24 dev + 48 locked test each are targets, not delivered sample counts. Before claims of effectiveness: author real cases and model-visible inputs; split template/source/constraint groups across both suites; collect actual backend/solver receipts and complete call trees; run two-person independent semantic calibration and adjudication; freeze versions/configurations; run the planned paired experiments and scenario-level uncertainty analysis. The manifest catches shared-template leakage, but source-document/constraint-group independence still needs the dataset design audit. No statistical significance or model superiority follows from these examples.

Old v0 scores are not rewritten. New-rubric diagnostics may be added only for legacy traces with sufficient evidence; a changed endpoint or capability contract requires a new eligible run. Future gold/rubric changes require a new version, preserved prior artifacts and consistent reassessment across strategies.
