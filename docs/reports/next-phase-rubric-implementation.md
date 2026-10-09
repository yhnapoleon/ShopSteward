# Next-phase rubric implementation ledger

Date: 2026-10-02. Scope: implementation plan Task 3; integrated design §§3.5 and 19.12–19.17. Existing untracked posttraining work, v0 scorer/contracts and historical results were preserved. No model calls, paid APIs, credentials, production writes or commits were used.

## Delivered

- New independent `posttraining/src/shopsteward_pt/case_eval/` namespace: frozen strict immutable models; exact case/trace/review binding; D1–D6 and Q1–Q6; critical overrides; independent true/false/null task outcome; explicit missing/pending/N/A states.
- Explicit `context-v1` `CallRecord` adapter with reserved→terminal deduplication, all-role usage support, incomplete-ledger handling, and unknown costs. It does not infer business success from assistant output.
- Offline `validate`, `score`, `report`, `schemas` commands, hash-bound input/output manifests, inclusive attempted-task denominators and cost/latency/strata reports.
- Nine reproducible synthetic dev examples, 32 illustrative agent annotations and generated outputs. Assets and outputs say `example`; **no actual research/model scores, no locked CE48/OPS48 set, no human calibration**.
- Six JSON schema exports and the complete usage/semantics guide in `posttraining/rubrics/agent_case_rubric_v1/README.md`.

## Verification ledger

TDD cycles were run before implementation: initial nine schema/scoring tests failed on the absent namespace; accounting/action tests failed on absent reporter, unrecognized action records and missing result invariants; CLI/adapter tests failed on absent modules; later regression tests exposed incorrect D6 credit, absent allowed-result/endpoint validation, unsupported-write acceptance, old-capability trace reuse and inconsistent cross-strategy gold. Each was fixed and rerun. The shipped examples are reproduced byte-for-byte and their expected outcomes checked.

Latest full posttraining suite run at this ledger update:

```powershell
.venv-pt/Scripts/python.exe -m pytest -c posttraining/pyproject.toml posttraining/tests -q -p no:cacheprovider --basetemp=var/next-phase-tests/rubric-critical-full
```

Result: **71 passed** (38 pre-existing tests and 33 new tests). No skips or failures. This includes all historical posttraining scorer/report/runner/command tests. Runtime integration outside this owned package is being verified by the context/backend workstreams and root; these results do not claim a complete repository integration suite.

Final combined verification also included the unchanged legacy policy contract tests:

```powershell
.venv-pt/Scripts/python.exe -m pytest -c posttraining/pyproject.toml posttraining/tests agent/tests/test_task_policy.py -q -p no:cacheprovider --basetemp=var/next-phase-tests/rubric-critical-regression
```

Result: **99 passed**. Final bundled-example validation passed (9/9/32 records, zero locked tests). Final scoped Ruff check passed; the two review-fix files were formatted with the root `.venv` Ruff installation (the posttraining runtime does not include Ruff).

Review correction: every predicate or semantic check with `critical_failure_code` is now included in the effective task-success gates, even if a contract omits it from its ordinary required list. Missing budget evidence produces `task_success=null`; an unreviewed critical semantic check also remains pending. Four regressions first failed against the previous scorer (including the false-success budget example), then passed after the fix. Confirmed critical failures remain false; the v0 scorer and historical outputs were not modified.

Example validation/scoring: 9 cases, 9 traces, 32 reviews, 0 locked cases; four separate endpoint/configuration report groups. JSON schema export: six schemas. Ruff check and format were run over only the new namespace, new tests and generator. Import/format issues found in the first lint run were fixed.

## Rulings

1. Use a namespaced evaluator rather than change historical v0 behavior; otherwise existing research numbers would become ambiguous.
2. Frozen observations are trusted oracle/exporter outputs with source-kind and evidence references. No heuristic JSON extractor or model-text business-success inference was added; absent state remains missing.
3. Require exact case-contract hash and version on every trace in addition to fixture identity. Capability/endpoint changes require an eligible new trace rather than silent rescoring.
4. Confirmed critical failures stay false even when other dimensions are pending. Invalid fixtures are excluded consistently across strategies and costs remain auditable.
5. Use only synthetic development examples now. Neither code-generated case quantity nor an agent annotation establishes independence, human calibration or model effectiveness.
6. Freeze intended partial-check anchors in each case. Useful unfinished Plan work can score D4=1 yet task_success=false; unavailable evidence is null, not partial credit or false by assumption.

## Remaining consuming-stage work

- Implement/validate real business-state observation export for each CE/OPS scenario; preserve snapshot/receipt/source artifacts alongside the complete runtime call tree.
- Author actual smoke/dev and disjoint locked suites; audit template/source-document/constraint grouping across both suites. Current template-partition checks do not establish all forms of independence.
- Have two team members independently calibrate semantic anchors and resolve disagreements; conflicting records currently remain pending until an explicit adjudicated review batch is supplied.
- Freeze actual model, prompt, profile, policy, builder/solver/adapter and pricing versions; run the planned real paired experiments and scenario-cluster uncertainty analysis.
- Do not report the demonstration success bounds as model accuracy, confidence intervals or project effectiveness.
