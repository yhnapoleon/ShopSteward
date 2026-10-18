# Next-phase Agent Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and superpowers:dispatching-parallel-agents for independent modules. Preserve existing user changes. Steps use checkboxes; record actual verification below.

**Goal:** Deliver working context-aware Mission conversations and supply-recovery Cases, optional bounded expert collaboration, a usable UI, and versioned offline evaluation.

**Architecture:** Extend the existing Python/LangGraph/FastAPI/PostgreSQL application and Nuxt UI. Deterministic planning owns quantities and money; existing approval/execution owns purchasing. Shared evidence and task contracts support single-agent and multi-agent execution; evaluation remains separate from model inputs.

**Tech Stack:** Existing uv Python workspace, SQLAlchemy/Alembic/PostgreSQL, LangGraph/OpenAI adapters, Nuxt/Vue/TypeScript, pytest/Playwright.

**Spec:** [Unified design v1.2](../specs/2026-09-30-next-phase-integrated-design.md).

## Global constraints

- Work in the requested current project on YH; preserve pre-existing unrelated changes and untracked posttraining work. No automatic commit/push/deployment or production database migration.
- Explicit user request authorizes implementation; do not ask again for design approval or execution-method selection.
- Case scope: one store/SKU, seven-day horizon, at most three offers, at most one emergency purchase. Minor-unit integer money; approved original orders remain in the timeline.
- Analysis never approves or sends purchases. Recovery materialization must use current versions and the existing approval/execution boundary.
- Preserve baseline Plan semantics and historical rubric results. New records/versioned paths must not silently reinterpret old records.
- Key files and credentials must not appear in output. Tests use dedicated test databases and deterministic/fake model transports; no paid research batch or external purchase is required for implementation.
- Multiagent depth one, at most two concurrent experts and one bounded follow-up. All roles share task budget and evidence permissions.
- Explicit runtime model profiles; absent usage remains unknown. Deployment availability of proposed model IDs is not assumed from this document.

## Usable outcome and validation boundaries

Users can revise constraints without losing earlier valid requirements, inspect a time-sensitive recovery analysis, select an eligible candidate for a pending Plan, and track actual execution state. Functional checks cover correct goals/amounts, no unintended writes, current-version enforcement, recovery/idempotency and trace completeness. Required local dependencies and real business invariants block only the affected path. Formal CE48/OPS48 effectiveness claims, human rubric calibration, paid model benchmarks, optional SFT and future multi-SKU/negotiation work remain their consuming research stages.

## Review focus

1. Long history and queued user edits must not leak future inputs or forget current constraints.
2. Packaging, zero/unset, negative values, insufficient evidence and expired offers must not produce a falsely executable Plan.
3. Worker restart, lost receipts and stale revisions must not duplicate purchases or publish obsolete results.
4. Existing Mission Plan approval must remain compatible; new recovery offers require revalidation through send.
5. Partial/unknown evidence, failed runs and reviews must not be scored as successful or cost-free.

## Task 1 — Context and model execution

**Files:** `agent/src/shopsteward_agent/context/`, `model.py`, `runtime.py`, `cases/`; `backend/app/agent_bridge/{composition,jobs,context_sources,context_repository}.py`; focused tests in agent/backend.

**Interfaces:** Maintain legacy `complete(messages, tools, tool_choice=...)` and `execute(...)`; introduce explicit context/profile contracts and optional bounded expert runner. Existing backend tool gateway remains the side-effect boundary. Communicate exact new integration signatures before consumers are changed.

- [x] Write and run failing tests for long-history retention, source replacement, admission, protocol preservation, truncation, profile/usage and shared-budget expert limits.
- [x] Implement deterministic model-view assembly and persistence/trace integration; wire the real Mission execution path.
- [x] Implement explicit adapter profiles and bounded expert execution, retaining legacy compatibility.
- [x] Run agent suite plus relevant backend unit/integration regression checks.

## Task 2 — Recovery Cases and business execution

**Files:** `backend/app/planning/recovery/`, `operations_cases/`, new Alembic migration, existing planning/execution/forecast consumers where needed, backend tests.

**Interfaces:** Authenticated `/api/v1/operations-cases` create/list/detail plus analyze/revise/materialize/control endpoints; responses expose revision, candidates, evidence, real Plan references and clear status. Match existing DTO/error/idempotency patterns. Publish schemas early for frontend integration.

- [x] Write and run golden numeric and real-state failure tests: budget 300 selects B20, budget 200 selects waiting; MOQ/pack/ETA/partial-arrival/UNKNOWN/version constraints.
- [x] Implement pure daily solver, persisted Cases/revisions/results and a real analysis producer using existing business sources.
- [x] Connect selected candidate to versioned pending Plan, preserve old approval/send behavior, and revalidate before writes.
- [x] Verify auth, revision conflicts, retries/duplicate requests, restart behavior and baseline Plan regressions.

## Task 3 — Rubric and offline evaluation

**Files:** New namespaced modules under `posttraining/src/shopsteward_pt/`, scripts, tests and versioned rubric assets; do not change old v0 scorer/results.

**Interfaces:** Frozen case contract + actual trace + rubric version + review records -> D1–D6, Q1–Q6, critical failures and tri-state task success. CLI supports offline scoring and reporting; no model calls required.

- [x] Run failing tests for partial vs false/pending, critical override, N/A, review binding and inclusive denominators/cost accounting.
- [x] Implement schema/scorer/report CLI and golden examples with reproducible manifests.
- [x] Verify legacy scorer regression suite and document research-dataset/reviewer status truthfully.

## Task 4 — UI and integration

**Files:** Nuxt recovery workspace/composables/types; existing task/work entry components; API export and runbooks. Root agent owns this task.

- [x] Add contract/UI checks for candidate comparison, budget revision, stale result handling, pending-plan adoption and accurate status.
- [x] Wire real Case endpoints into the current workspace; surface evidence, assumptions and next action; reuse existing approval UI.
- [x] Connect worker/processor, schema registration and local startup as required by actual producer contracts.
- [x] Run frontend typecheck/build and relevant browser/API tests; generate API types from actual OpenAPI.

## Task 5 — Cross-module verification and handoff

- [x] Run combined unit and isolated PostgreSQL integration tests; record skipped/unavailable dependencies explicitly.
- [x] Run a fresh code review of changed paths and fix important findings with regression tests.
- [x] Document startup flags, migrations, user flow, verified capabilities, remaining research work and exact commands/results.

## Implementation ledger

- 2026-10-02: Inspected current YH checkout at `30bed9f`; existing changes retained. No next-phase product modules present. Existing WorkItem intake explicitly lacks an actual processor.
- Ruling: use current checkout as requested, with module ownership and no automatic commits; the pre-existing working-tree version is required by this project, so a clean HEAD-only checkout would omit the existing task-policy/evaluation work.
- Ruling: implementation is authorized by the current request; prior design is the binding specification. Formal research evidence is distinct from functional delivery and will not be fabricated.
- 2026-10-03: Core implementation is integrated in the current checkout: source-aware Mission context, frozen model profiles and call ledger, bounded Case experts, deterministic recovery solver, persisted revisions and guarded pending-Plan adoption, opt-in durable follow-up, frontend controls/Inspector, and independent rubric v1.
- Scope ruling: these checkboxes describe this core implementation phase, not every roadmap item in the integrated design. Automatic WorkItem-to-Case routing, PDF applicability/ETA-change producers, general semantic compaction, heterogeneous collaboration-strategy runners and actual business-outcome export remain follow-up implementation; locked CE48/OPS48 sets, human calibration and measured model comparisons remain research work. See the explicit boundaries in the [delivery report](../../reports/2026-10-02-next-phase-delivery.md).
- Final review: fixed selected-supplier/amount binding, historical-Plan adoption locks, new-Case/recheck lifecycle, missing Chat reasoning effort, incomplete critical rubric evidence, obsolete expert sends and mutation-intent boundaries. The last two findings were reproduced with pure functions and Runtime/gateway regressions, corrected, and independently confirmed closed. Same-message no-save prohibitions win; later messages can explicitly authorize a specific supported write.
- Environment fixes: isolate PostgreSQL suites to avoid global queue cleanup interference; use repository-local pytest temporary directories; rename colliding test modules; use a complete real-browser fixture; use Proactor only for Windows browser tests that start Node subprocesses. Preserve production validation and user database state.
- Final verification (2026-10-03): backend **605 passed / 0 skipped** including all three opt-in real browsers; agent **124 passed / 0 skipped** including PostgreSQL; posttraining **71 passed**; frontend **27 passed**; separate real recovery HTTP/browser flow **8 checks passed**. Nuxt typecheck/build, generated API contracts, scoped Ruff and diff whitespace checks passed. No paid model or real supplier calls. Exact final results and remaining scope are recorded in the delivery report.
