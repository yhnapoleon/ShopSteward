# B0-04 Alerts, Dashboard and Timeline Implementation Plan

> Execute the user-approved B0 design in the current task with writing-plans, TDD and verification-before-completion. Preserve the existing uncommitted B0 work; no commit/push requested. Use requesting-code-review for independent review.

**Goal:** Persist risk episodes from fenced Mission checks, allow acknowledgement, and expose read-only dashboard/history.

**Architecture:** app/alerts owns typed risk evaluation and persistence. check_mission reconciles evaluated risks in its existing store/Mission/lease transaction. Read APIs use existing authorization and condition-bound keyset pagination; dashboard uses a short read-only REPEATABLE READ transaction.

**Tech Stack:** Existing PostgreSQL, SQLAlchemy/Alembic, FastAPI/Pydantic, pytest. No new dependencies.

**Spec:** docs/backend-development.md sections 2.4, 4.4, 4.5, 8.2 and B0-04; docs/api/backend.openapi.json.

## Rules and boundaries

- Add get_dashboard, list_alerts, acknowledge_alert, list_mission_timeline: 18 total runtime operations.
- One active episode per store/Mission/SKU/type (ACTION_EXCEPTION additionally action_id); unique partial index on a stable scope key. Resolved recurrence gets a new ID. Updates never advance State.
- STOCKOUT_RISK uses current demand minus stock and eligible inbound, before proposed purchase; WARNING normally, CRITICAL when on-hand stock is zero. CASH_CONSTRAINT is CRITICAL below the cash floor; WARNING when covering the gap at valid MOQ/pack costs more than available headroom. A rejected oversized candidate alone is not a risk.
- INCONCLUSIVE creates DATA_STALE WARNING immediately and preserves other risks. A conclusive check resolves absent evaluated risks. SKIPPED neither creates nor clears alerts. Pause/terminal control alone does not prove risk recovery.
- Acknowledgement requires store operator/admin and Idempotency-Key. OPEN→ACKNOWLEDGED; repeated acknowledgements are no-ops. RESOLVED rejects new acknowledgements with409 ALERT_RESOLVED. Escalation reopens the same episode, preserving prior actor/time and append-only timeline audit.
- Timeline records creation/escalation/resolution/acknowledgement and each completed check; repeated unchanged risk checks do not generate duplicate risk-transition entries. Check references carry Mission/Plan versions. Historical job IDs are plain text, not fake artifact references.
- ACTION_EXCEPTION lifecycle storage is supported, but no action state or automatic action alerts are invented before B0-05. DATA_STALE is persisted by checks; dashboard freshness updates on read without writes. Periodic source/check dispatch remains B0-06.
- Dashboard counts ACTIVE Missions and OPEN/ACKNOWLEDGED alerts, last completed non-SKIPPED Mission check, and actual pending check due times or enabled Schedule times. No source→UNKNOWN; failed/expired source→STALE. Plan/alert facts may lag current State and retain their original version.
- Alert ordering uses immutable first_seen_at/id; timeline created_at/id. Cursors bind all filters, authorization precedes replay, and unknown/cross-store Missions are404.

## Task 1 — Rules and persistence

Files: app/alerts/{schemas,rules,models,repository}.py, migration0004_alerts_history, tests/unit/test_alert_rules.py.
- [x] Write failing SC01, cash shortage, MOQ/pack, zero-stock severity and invalid-candidate tests; run them.
- [x] Implement evaluate(snapshot, candidates) returning typed findings; reconcile(session, mission, findings, evaluated_types, state_version, plan_id) under caller-held locks.
- [x] Add alerts uniqueness/status/severity/version constraints and timeline pagination index; migrate dedicated test DB.

## Task 2 — Check lifecycle and audit

Files: app/planning/jobs.py, app/missions/repository.py, tests/integration/test_alerts.py.
- [x] Test100 unchanged checks→one episode/one creation entry; acknowledgement→escalation→recovery→new episode, source staleness preserves risks, no State changes, expired lease rolls back all derived rows.
- [x] Reconcile after publication/reuse/suppression with the chosen Plan ID, before the fenced JobRun completion; add completed-check audit in after_complete.
- [x] Run PostgreSQL tests including concurrent acknowledgements and original-command replay.

## Task 3 — Read APIs and acknowledgement

Files: app/alerts/router.py, app/reporting/{schemas,repository,router}.py, app/main.py, tests/integration/test_reporting.py.
- [x] Test actual response schemas, roles/cross-store visibility, cursor filters, pagination, unchanged State/queue/ledger after GET, fresh/unknown/stale dashboard and actual next-check time.
- [x] Implement dashboard(session, store_id, settings) within read-only REPEATABLE READ; list alerts/timeline and acknowledgement command receipts using existing store→Mission locks.
- [x] Register four routes; update expected runtime routes and export actual OpenAPI.

## Task 4 — Verification and handoff

- [x] Run backend/simulator suites, Ruff/format, migrations/drift, contract validator; independently review risk semantics and transaction boundaries.
- [x] Real separate API/worker/simulator smoke: initial Plan+stock risk, acknowledge without State changes, read dashboard/history; restart and reread persisted acknowledgement.
- [x] Update runtime manifest, smoke evidence, backend README, architecture/design scope and PROJECT_CONTEXT. Record exact tests and remaining B0-05/06/07 scope.

Final validation: backend87 + simulator2 passed without skips; independent review found no important defects. Four new APIs (18 total), migration0004, drift/Ruff/format/contracts and real API/worker restart smoke passed. Resolution retains last risk facts/version. Reference adds alert to both shared design schemas. No commit/push.
