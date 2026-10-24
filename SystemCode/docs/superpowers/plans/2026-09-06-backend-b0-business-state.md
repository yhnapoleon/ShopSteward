# B0-02 Business State and Simulator Bootstrap Implementation Plan

> Execute in the current task, preserving B0-01 and existing uncommitted design work. Use test-driven-development and verification-before-completion. The user authorized continuing backend construction.

**Goal:** Persist initial business state and source events, expose authorized catalog/event intake, and initialize a real persistent simulator through the independent worker.

**Architecture:** Backend operations own store, stock, catalog, forecast, source cursor and ledger tables. Simulator is a separate HTTP process with its own PostgreSQL database and migrations. Network requests happen outside backend write transactions; derived business writes and JobRun completion share a lease-fenced transaction.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/asyncpg/Alembic stack; no new infrastructure dependency.

**Spec:** docs/backend-development.md sections 3/5/9/14/15 and docs/simulation-contract.md.

## Constraints

- B0 has seven work packages. This plan implements B0-02; Mission planning and approval execution retain their later packages.
- Integer minor currency units; nonnegative inventory/cash; store lock precedes cursor and job locks.
- INIT is immutable and replay must never reset an existing projection. Event identity, sequence, content and batch command identity are checked in PostgreSQL transactions.
- Unknown purchase/receipt actions fail closed with a conflict. Full accepted-purchase reconciliation and positive receipt acceptance are completed alongside B0-05, when an authorized Action exists; this dependency is explicitly recorded, never represented as completed SC01.
- Simulator create/events only; no undocumented endpoint mutates the simulation world. Purchase and advance remain unregistered until implemented.
- No periodic scheduler yet. Initialization queues one source sync; a local CLI can enqueue further syncs. Freshness is granted only to a validated caught-up page and expires by real time.
- Stable command IDs permit replay after remote commit/local failure. Job-derived writes roll back if the final lease check fails.

## Task 1 — Operations projection

Files: backend/app/operations/{schemas,models,repository}.py; backend/migrations/versions/0002_business_state_business_state.py; backend/tests/integration/test_operations.py.

- [x] Write failing PostgreSQL tests for immutable initialization, sale/demand projection, duplicate/conflicting events, sequence gaps, all-batch rollback, wrong store/SKU, unknown receipts and concurrency.
- [x] Add typed contract DTOs and relational operations tables; migrate dedicated test database.
- [x] Implement initialize(session, ScenarioRun), ingest(session, EventBatch, command_scope, key), get_state/get_catalog and caught-up source freshness.
- [x] Verify all projection tests against PostgreSQL, including replay after a fresh session.

## Task 2 — Persistent simulator bootstrap

Files: simulation/simulator/{main,config,db,models,repository}.py; simulation/migrations/; simulation/tests/; simulation/README.md and pyproject.toml.

- [x] Write failing tests for authenticated create/replay, independently constructed app instances, empty event pages and ahead-cursor rejection.
- [x] Implement create/events against a separate PostgreSQL database with its own migration and service token. Persist the original SC01 snapshot and transactional run sequence.
- [x] Verify HTTP response shapes against services.openapi.json; unimplemented purchase/advance are absent from runtime OpenAPI.

## Task 3 — API and worker integration

Files: backend/app/operations/{router,jobs,client}.py; backend/app/scheduling/{handlers,runner}.py; backend/app/core/config.py; backend/app/cli.py; backend/tests/integration/test_bootstrap.py.

- [x] Write failing tests for dev/admin gating, scoped service event intake, catalog store authorization, command replay and expired-lease rollback of business writes.
- [x] Implement create_dev_scenario returning a replay-stable 202 receipt, get_catalog and ingest_event_batch. Disable dev routes in production.
- [x] Add initialize_scenario and sync_events handlers. Extend handler finalization so local projection, follow-up enqueue and lease-fenced completion commit atomically.
- [x] Verify remote success/local lease loss recovery, source page validation and freshness expiry. Run separate API/simulator/worker processes and persist smoke evidence.

## Task 4 — Verification and delivery

- [x] Run all backend and simulator tests, Ruff and Alembic drift checks; validate design/runtime contracts.
- [x] Review changed concurrency/authentication boundaries; reproduce/fix material findings.
- [x] Update runtime schemas, implementation manifest, README and PROJECT_CONTEXT with actual capabilities and remaining purchase/arrival dependency. No commit/push requested.

## Execution evidence — 2026-09-06

This bootstrap/core slice is verified; the complete B0-02 positive receipt criterion remains dependent on B0-05, as scoped above. Backend 50 tests and simulator 2 tests passed with no skips. Ruff/format and Alembic drift checks passed, backend revision0002_business_state and simulator revision sim_0001. Design contracts (53 examples/23 shared schemas) and both exported runtime schemas validated.

Independent review findings on cross-run command identity, source/local forecast versions, cursor conflict codes and apply deadline were reproduced in failing tests and fixed. A stale source with remaining pages cannot be reported fresh. API/simulator/worker ran as separate processes; after restarting all three, the original simulator run and backend command replayed unchanged, the CLI state remained cash100000/on_hand20/version1, and a new CLI sync succeeded. Live schemas match the exported7 backend/3 simulator routes. Evidence: docs/api/b0-02-bootstrap-smoke-result.json. No Git commit or push.
