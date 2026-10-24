# B0-05 Approval, Purchase and Reconciliation Plan

> Execute approved backend/simulator contracts with TDD and independent reviews. Simulator subtask owns simulation/**; backend implementation stays in this task. Preserve uncommitted B0-01/04 work; no commit/push.

**Goal:** Exact approval → one durable Action → simulator purchase → unique accounting, with safe unknown-result recovery and positive goods receipt validation.
**Architecture:** Store→Mission/Plan→Action locks; pre-send reservation/state transition fenced by current JobRun lease. HTTP outside transactions. Receipt publication/ledger/timeline/alerts fenced with job completion. An Action-specific recovery scan requeues orphaned approved/uncertain work; executing Actions always query original ID before any guaranteed-idempotent resend. Unknown retains reservation/store gate.
**Spec:** docs/backend-development.md sections4/6/8/9, docs/simulation-contract.md and both OpenAPI contracts.
**Stack:** Existing async FastAPI/PostgreSQL/SQLAlchemy/Alembic, no new dependency.

- [x] Simulator: purchase/query and atomic four-stage advance with independent migration/tests and exact contract DTOs; no backend table access.
- [x] Approval/API: PlanDecision, immutable Approval, Action/request snapshot and Store gate; create/reject/get action; role/store/command/plan/hash/current state/time checks, no q0 Action. Migration0005.
- [x] Execution: lock/revalidate/reserve/increment state once, execution version recorded; lease loss never permits pre-send writes; late valid receipts accepted despite state/time/Mission changes; 404 only resends same request/key. Unknown/pending preserve reserve; explicit reject releases; conflict preserves evidence and stops automatic mutation.
- [x] Event integration: accepted HTTP/event share action-key ledger effect, receipt quantities bounded and deduplicated; receipt-before-local-acceptance prefetches remote evidence outside locks, whole event batch remains atomic. Action alerts scoped by action, control cancels unsent work but preserves sent reconciliation.
- [x] Recovery: persistent Action next-reconcile time (5/10/30/60 seconds); enqueue one active execute/reconcile per action under store lock, recover orphaned work separately before JobRun claim (no inverted locks).
- [x] Dev advance endpoint and worker: stable job ID passed to simulator then sync events; enables real receipt acceptance and full numeric SC01 smoke, broader recurring/load/fault matrix remains B0-06/07.
- [x] Tests: concurrent approval, replay/conflict/forgery, stale/expired/source/cash gates, lost response and404, reserve/lease/restart, event/receipt ordering, overreceipt/rollback/conflict evidence, cancelled Mission late receipt, full SC01 40 then20.
- [x] Verify: all suites, migration/drift, runtime/design contracts, independent code reviews, real API/worker/simulator + restart smoke; update READMEs/manifest/PROJECT_CONTEXT with exact scope.

Verification evidence: backend115 tests and simulator12 tests passed without skips; separate API/worker/simulator SC01 and restart record in docs/api/b0-05-execution-smoke-result.json. Independent reviews resolved protocol conflict/null/nonfinite evidence and recovery starvation; no commit/push. Recurring dispatch remains B0-06.
