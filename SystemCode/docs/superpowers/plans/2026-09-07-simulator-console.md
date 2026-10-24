# Simulator Console Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent dashboard task; the parent owns the transaction/API implementation, integration and final verification. Execute the approved work without another approval checkpoint.

**Goal:** Persist configurable synthetic scenarios and expose a working local dashboard for sales, demand and receipt triggers with backend synchronization visibility.

**Architecture:** Extend the existing simulator with SANDBOX initialization and typed transactional triggers; retain SC01 behavior. Serve a local-only console from the same FastAPI app, keep credentials on the server, and use fixed backend HTTP endpoints for linked creation and observations. Source facts flow to backend through its existing workers.

**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/PostgreSQL/Alembic/HTTPX; plain local HTML/CSS/JavaScript.

**Spec:** `docs/research/2026-09-07-simulator-console-research.md`, explicitly approved by the user on 2026-09-07 including database writes and dashboard.

## Global constraints

- Docker Desktop is started manually by the user. Preserve existing data and credentials.
- Work in the current YH checkout; frontend/ is owned by the separate product work and stays untouched.
- CNY integer minor units; integer piece quantities. Purchases are accepted through the existing supplier protocol and approved by backend.
- All source mutations and command records commit atomically under the Run lock. GET requests never mutate.
- Dedicated test databases only for automated tests. Development acceptance creates new named synthetic runs and preserves them.
- No RAG/model calls, live external purchases, reset/delete controls, arbitrary event JSON or generic proxy.
- Source sequence and backend state_version are different. Observation HTTP snapshots may differ in time.

## Task 1 — durable SANDBOX and typed triggers

Files: simulator/schemas.py, models.py, repository.py, controls.py, control_schemas.py, main.py, db.py; migration sim_0003_controls.py; tests/test_controls.py.

- [x] Write tests using real HTTPX ASGI requests and PostgreSQL: configured seed persistence; concurrent same-key sale once; invalid sale rollback; demand revision; partial/full arrival and cross-run rejection; SC01/SANDBOX mode separation; stale expected_sequence and restart replay.
- [x] Run the new tests and observe failure on unsupported SANDBOX/controls.
- [x] Add `ScenarioParameters` and `ScenarioCreate(scenario: SC01|SANDBOX, label?, parameters?)`; SC01 rejects overrides. Preserve old SC01 command payload when optional fields absent.
- [x] Add Run.configuration JSONB with SC01 default and additive migration, preserving historical snapshots.
- [x] Implement `list_runs(session, before, limit)`, `get_run(session, run_id)`, `trigger_run(session, run_id, key, request)`.

Trigger request interface (kind discriminates; all require expected_sequence):
```json
{"kind":"sale","expected_sequence":0,"quantity":5,"unit_price_minor":2000,"advance_seconds":3600}
{"kind":"demand","expected_sequence":1,"remaining_demand":90,"advance_seconds":0}
{"kind":"receipt","expected_sequence":3,"action_id":"action-id","quantity":10}
```
Receipt quantity null/absent means the remaining order quantity. Return `{scenario_run_id, first_sequence, last_sequence, simulation_time, before, after, events}`. Reject insufficient stock, excess receipts, cross-run orders and elapsed horizon without effects; validate final State bounds before commit.

- [x] Service APIs: GET `/sim/v1/runs`, GET `/sim/v1/runs/{run_id}`, POST `/sim/v1/runs/{run_id}/triggers`, all service authenticated. Use repeatable-read read-only snapshots for detail/list/events. Existing APIs stay compatible.
- [x] Run original and new simulator tests, migration drift and Ruff.

## Task 2 — local console boundary and backend link

Files: simulator/console.py, console_backend.py, config.py, pyproject.toml, tests/test_console.py; backend/app/operations/schemas.py and router.py; simulation/tests/test_console.py (backend DTO compatibility).

- [x] Test disabled console, wrong Host/Origin/remote peer/cross-site POST, missing write header, and no credential exposure. Test direct persistence through the console's own routes.
- [x] Register `/console/` and static resources only when `SIM_CONSOLE_ENABLED=true`. Local API prefix `/console/api`; requests enforce loopback, local Host, same-origin browser access, JSON plus `X-Simulator-Console: 1` for writes. No arbitrary proxy URL.
- [x] Console APIs mirror typed simulator operations: GET status, GET runs, GET run detail, GET events, POST runs, POST triggers and POST advance. All POST requests require `Idempotency-Key`.
- [x] `POST /console/api/linked-runs` forwards approved ScenarioCreate to backend `/dev/v1/scenarios`; return 202 JobAccepted. GET `/console/api/jobs/{id}` reads the job and resolves its references on success.
- [x] GET `/console/api/runs/{run_id}/backend` uses the run's store_id and returns `{status, dashboard, source_sequence, missions, plans, alerts}`. Read backend dashboard, sales context, missions and alerts through fixed paths; 404 means not imported, dependency failure means unavailable. No backend DB access.
- [x] Backend ScenarioCreate accepts the identical SANDBOX seed contract. Existing initialization worker forwards it unchanged; no new worker type. Preserve old SC01 omitted-field hashes.
- [x] Verify source event DTOs can be consumed by the real backend, then real worker/HTTP acceptance in Task 4.

## Task 3 — usable dashboard

Files: simulation/simulator/static/index.html, console.css, console.js. Delegated UI task; no Python or frontend/ edits.

- [x] Build responsive Chinese control dashboard: persistent run sidebar, preset/custom creation form, state cards, sales/demand/receipt forms, event history, backend observation panel, service status and explicit synthetic-data labels.
- [x] Use only relative console APIs. Store only selected run id locally; no credentials. Disable duplicate submissions, retain original key/body for uncertain request retry, refresh current sequence after conflict, and present actionable error codes.
- [x] New run request `{scenario:'SANDBOX',label,parameters:{cash_minor,on_hand,remaining_demand,unit_price_minor,minimum_order_quantity,pack_size,lead_time_seconds,horizon_days}}`; SC01 sends scenario only. Presets populate editable values without auto-submitting.
- [x] Run list `{items:[{scenario_run_id,store_id,scenario,label,created_at,simulation_time,last_sequence}],next_cursor}`. Detail adds `{state,initial_snapshot,configuration,orders,step_index}`; each order `{action_id,status,quantity,received_quantity,remaining_quantity,eta,total_minor}`.
- [x] Expose original SC01 advance button only for SC01, SANDBOX trigger forms only for SANDBOX. Receipt requires actual pending order and explains advancing to ETA. No purchase-approval shortcut.
- [x] Event list uses existing EventPage and after_sequence pagination. Source read state_version is a bootstrap field, not a backend version: do not display as live business version.
- [x] Validate with JS syntax check then browser execution against real server, including creating a persistent run and firing an event. No fabricated successful fallback data.

## Task 4 — running services, acceptance and handover

Files: simulation/tools/verify_console.py, simulation/README.md, .env.example, API runtime exports, test report, PROJECT_CONTEXT.md, HANDOVER.md.

- [x] Migrate simulator dedicated test DB, run focused suites, then backend+agent and simulator regression sequentially against dedicated databases. Export runtime contracts and verify compatibility.
- [x] Verify simulator process identity, stop only own old simulator, migrate development simulator DB additively and restart with console enabled. Migrate backend development DB to existing head before starting a matching API/business worker. Keep Agent disabled for this work.
- [x] Use server-side existing configured admin identity for backend link; do not print/write token into browser artifacts or tracked files.
- [x] Create new linked acceptance run and Mission through real APIs; approve an exact backend Plan in the acceptance script, await actual accepted purchase, partially receive, sell, revise demand, fully receive. Assert exact source/backend cash, receivables, stock and source_sequence. Retry a trigger with original key and assert no duplicate effect.
- [x] Restart owned simulator and verify persisted run and trigger replay. Preserve named demo runs and report result IDs; never reset existing stores.
- [x] Perform browser interactions and inspect layout at desktop/mobile sizes. Leave the working dashboard open in Codex and document exact startup steps.
- [x] Independent code review of transaction, authentication and HTTP integration changes; fix verified defects and rerun affected checks.
- [x] Save a concise test/acceptance report and update project handover with actual ports, migration heads, limitations and Docker preference. No automatic commit/push needed for this local delivery.

## Execution record

- 2026-09-07: User approved implementation. Existing research edits retained. Baseline simulator was 12 passing; baseline HEAD 4389747.
- Design decision: local UI task runs independently alongside parent transaction work; one final independent review covers integration. No extra worktree needed because only simulation and narrow backend contract files change, and product frontend files are excluded.

- Completion: persistent source/API and console implemented; additive development/test migrations applied. Simulator 23 passed, backend+Agent 226 passed, Node UI async regression 3 passed. Real HTTP 13 + restart 3 checks passed; browser creation/sale/demand/partial+full receipt and backend sync passed.
- Independent reviews found UI pending-retry/selection/pagination races and launcher environment precedence; fixed and verified. No product frontend edits, commits or model calls. See docs/reports/simulator-console-test-report.md for scope and saved evidence.
- Acceptance helper initially failed in the final preexisting-run comparison expression after business checks; fixed, retained first-attempt evidence and reran successfully.
