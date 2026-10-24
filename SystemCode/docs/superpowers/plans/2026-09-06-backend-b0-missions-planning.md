# B0-03 Missions and Deterministic Planning Implementation Plan

> Execute in the current task using the existing approved B0 design, writing-plans/test-driven-development and verification-before-completion. Preserve prior uncommitted work on codex/backend-b0-foundation; no commit/push requested.

**Goal:** Create/control/read Missions and run durable checks that publish immutable, versioned candidate comparisons with complete decision snapshots.

**Architecture:** Mission and planning modules share the B0-02 operations state and independent worker. Prepare reads a short read-only REPEATABLE READ snapshot. Publish locks store then mission, validates input versions/time and commits the Plan, timeline and JobRun outcome under the existing lease fence. Stale computation queues one follow-up after current job completion in the same transaction.

**Tech Stack:** Existing FastAPI/Pydantic, PostgreSQL, SQLAlchemy/Alembic and pytest; no new dependency.

**Spec:** docs/backend-development.md sections 3/4/6/8/10/14; docs/api/backend.openapi.json.

## Scope and constraints

- Create/list/get/control Mission, request check, list/get Plan: seven new operations. Approval/Action, alert/timeline HTTP and schedule PATCH remain later phases.
- One ACTIVE/PAUSED Mission per store/SKU enforced in PostgreSQL. Operator creates/checks/pauses/resumes; approver completes/cancels; admin allowed. All permissions/store visibility precede command replay.
- Store schedule interval as a disabled Schedule with next_run_at=null until B0-06 enables periodic dispatch. Initial creation/resume queues one check.
- Quantities and money are integers. Candidate ranking is shortage, then quantity. Zero quantity proposes no purchase. MOQ, pack, available cash floor, arrival horizon and inbound ETA are checked.
- Fixed forecast uses current remaining demand. Expired fixed data may be locally revalidated only after source catch-up; renewal persists a new local version and increments store state version, never restores initial demand.
- No network inside a backend write transaction. No decisions from stale/unknown source data, missing inbound evidence or expired offers. INCONCLUSIVE and SKIPPED remain durable job results.
- Immutable Plan JSON, separate mutable status; min(TTL, forecast expiry, offer expiry), canonical decision-v1 hash, semantic input reuse excludes sync/evaluation timestamps. Expired plans never extended in place. Same-input rejected recommendations are suppressed except explicit manual recheck.
- B0-03 adds inbound record structure for correct snapshots; only future confirmed purchase reconciliation may populate it in normal operation.

## Task 1 — Pure planning

Files: backend/app/planning/{schemas,engine}.py, backend/tests/unit/test_planning.py.

- [x] Add failing tests for SC01 40/80, zero/no feasible choices, MOQ/pack, inbound ETA, late new purchases and canonical hash.
- [x] Implement typed wire DTOs, finite candidate calculation and complete Plan generation.
- [x] Run pure tests and validate plan response against the design schema.

## Task 2 — Mission persistence and API

Files: backend/app/missions/{models,repository,router}.py, backend/app/core/pagination.py, migration0003_missions_planning, backend/tests/integration/test_missions.py.

- [x] Test create/replay/conflict/concurrent uniqueness, role/store boundaries, control version checks and terminal state rules; test bounded condition-bound pagination.
- [x] Persist Mission/Schedule/Plan/Timeline/inbound rows. Implement command receipts, initial/manual check merging and stable list/detail APIs.
- [x] Apply migrations to development/test databases and run integration tests.

## Task 3 — Snapshot and worker publication

Files: backend/app/planning/{snapshot,jobs}.py, backend/app/scheduling/{handlers,runner}.py, backend/tests/integration/test_planning_jobs.py.

- [x] Test immutable snapshot publication, unchanged-input reuse, expiration, source staleness, fixed forecast renewal after sales, concurrent mutation/pause, lease loss and stale-result follow-up.
- [x] Implement read snapshot and FixedForecastProvider, version/time checks, plan supersession, timeline and atomic follow-up after JobRun completion.
- [x] Register check_mission and validate end-to-end persistent job outcomes against real PostgreSQL.

## Task 4 — Verify and document

- [x] Run backend/simulator suites, Ruff/format, migrations/drift and design/runtime contract checks; independently review major correctness boundaries.
- [x] Run actual API/simulator/worker smoke from fresh scenario through Mission to recommendation40; restart/re-read persisted result.
- [x] Update implementation manifest, runtime OpenAPI, backend README and PROJECT_CONTEXT with precise B0-03 scope and remaining B0-04/05/06/07 work.

Validation: backend74 + simulator2 passed; Ruff/format, migrations/drift and contracts passed. Independent review findings fixed with regressions. Separate-process planning and API/worker restart smoke recorded in docs/api/b0-03-planning-smoke-result.json. No commit/push.
