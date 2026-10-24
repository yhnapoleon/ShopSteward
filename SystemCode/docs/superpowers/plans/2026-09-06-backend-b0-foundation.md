# B0-01 Backend Foundation Implementation Plan

> Execution: current task, inline. The user authorized starting backend construction after approving the v0.2 design. Preserve the existing uncommitted design documents; work on `codex/backend-b0-foundation` without changing other modules' implementation.

**Goal:** Provide a runnable API, PostgreSQL migrations, authentication/error boundaries and a durable worker probe that demonstrates queue execution without claiming business functions are implemented.

**Architecture:** FastAPI and an independent async worker share SQLAlchemy models and PostgreSQL. Business routes remain unregistered until implemented. A technical `worker_probe` job verifies the runner and returns a typed result; it does not run an inventory check or a purchase.

**Tech Stack:** Python >=3.11 (local verification 3.12), FastAPI/Pydantic, SQLAlchemy 2.x + asyncpg, Alembic, uv, pytest, PostgreSQL.

**Spec:** `docs/backend-development.md` v0.2, sections 2/5/6/7/12/13/14; `docs/simulation-contract.md`.

## Global constraints

- Amounts will be integer minor units; B0-01 introduces no inventory or cash business tables.
- No import-time database connection/migration, API background worker, Agent or simulator process.
- PostgreSQL integration tests are required for claiming queue atomicity; SQLite is not a substitute.
- Each async job/request has its own session. Claims and completion use short transactions and database time.
- No purchase handler until the execution workflow exists. Expired external-write jobs must never be blindly retried by the generic runner.
- Runtime OpenAPI includes only implemented routes; the existing contract remains the planned target.

## Files and responsibilities

`backend/app/core/{config,errors,logging}.py`: typed environment settings, error types, structured safe logs.
`backend/app/db/{base,session}.py`: metadata, lazy engine/session lifecycle and schema readiness.
`backend/app/api/{schemas,dependencies,errors,router}.py`: response DTOs, server-owned token grants, error mapping, health/monitoring/job reads.
`backend/app/main.py`: app factory and lifespan; `backend/app/__main__.py`: API launch.
`backend/app/scheduling/{models,repository,runner,handlers}.py`: durable queue, lease token, guarded completion, heartbeat and registered probe.
`backend/app/{worker,cli}.py`: independent worker and local technical enqueue command.
`backend/migrations/`: explicit Alembic schema creation for job_runs and worker_heartbeats.
`backend/tests/{api,integration}/`: public API/error/auth contracts and real PostgreSQL queue tests.
`infra/compose.yaml`: loopback-only PostgreSQL development service with pinned image version.
`backend/README.md`, `.env.example`, runtime OpenAPI and PROJECT_CONTEXT: actual startup and evidence.

## Task 1 — API and settings

- [x] Add failing tests for `/health/live`, readiness when database is unavailable, missing/invalid/service tokens on admin monitoring, request IDs, hidden B2 routes, and uniformly shaped422 errors.
- [x] Run `uv run pytest tests/api -q` and observe missing application failure.
- [x] Implement `create_app(settings: Settings | None = None) -> FastAPI`, lazy `Database`, `Principal`, server-owned token role/store grants and DTOs. Health live returns `{"status":"ok","component":"backend"}`; ready returns503 for inaccessible/unmigratedDB. A service grant cannot become admin by sending request fields.
- [x] Run API tests to green. Settings validation rejects zero lease/concurrency, invalid DB drivers and malformed/duplicate token mappings. No default reusable token is shipped.

## Task 2 — Migration and durable queue

- [x] Add failing PostgreSQL tests for idempotent enqueue, conflicting payload, simultaneous claims, wrong/expired token completion, and re-claim of expired retry-safe work.
- [x] Implement `enqueue(session, *, job_type, dedup_key, store_id=None, mission_id=None, payload=None) -> JobRun`, `claim(session, *, lease_seconds, job_types) -> JobRun | None`, and `complete(session, job_id, token, result) -> bool` with explicit caller-owned transactions. Persist `job_runs` and `worker_heartbeats` via revision `0001_foundation`.
- [x] Configure an isolated development PostgreSQL database and dedicated `shopsteward_test`; migrate both. Run `uv run pytest tests/integration -q` against real PostgreSQL.
- [x] Verify a second claimant cannot receive a locked job and old lease tokens cannot change result/status. No external effect is inferred from a queue status.

## Task 3 — Worker and operational HTTP

- [x] Test registered `worker_probe` reaches SUCCEEDED through actual runner and yields a result after a new session/process reads it. Test unsupported job types are not claimed as successful, and a rejected token leaves job status unchanged.
- [x] Implement bounded worker, database heartbeat and stop signal. The probe alone is marked retry-safe. `--once` claims and finishes at most one job; continuous mode reports heartbeat even when idle.
- [x] Implement admin monitoring and authorized GET job_run; global technical jobs are admin-only, scoped jobs require server-owned store grants. Sources are empty until source sync exists, never fabricated as FRESH.
- [x] Launch actual API/worker separately; enqueue a probe, query its result, verify Swagger/readiness and graceful stop.

## Task 4 — Deliver and verify

- [x] Lock dependencies with uv; export actual OpenAPI without connectingDB; validate responses against design schemas for implemented operations (including the documented technical job enum extension).
- [x] Run pytest, ruff, Alembic current/check and the existing design-contract validator. Record exact passed/skipped tests; do not label B0 business implementation complete.
- [x] Document Windows/Docker startup, environment token format, tests, probe commands and remaining B0-02 onward. Update PROJECT_CONTEXT and API implementation manifest. Preserve all existing user changes and do not commit/push unless needed or requested.

## Execution evidence

Completed B0-01 on2026-09-06:28 tests passed (16API/12PostgreSQL); Alembic0001_foundation and no drift; realAPI/CLI/worker smoke recorded in docs/api/b0-01-smoke-result.json. Independent review findings on malformed bearer/driver errors and pre-claim shutdown were reproduced and fixed. Business workflows and simulator remain outside this work package. No commit or push.
