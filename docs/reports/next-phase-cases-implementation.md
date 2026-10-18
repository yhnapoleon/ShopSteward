# Recovery Cases implementation ledger

Date: 2026-10-02. Scope: implementation Task 2 and the deterministic/worker parts of Task 4. Design basis: integrated design v1.2 §§3, 5–6, 11–15, 17 and 19–20.

## Delivered behavior

- Authenticated owner/store-scoped create/list/detail/analyze/revise/materialize/control/events API under `/api/v1/operations-cases`. Every mutation uses command receipts and an explicit revision where applicable. Inputs, source snapshots, candidate comparisons and progress events persist in PostgreSQL. Analysis is an actual deterministic producer reading current Mission, cash, inventory, structured supplier offers, unreceived inbound quantities and eligible v6 evidence or an explicit user daily-demand scenario. A total alone produces `DAILY_DEMAND_REQUIRED`, never an invented uniform profile.
- Seven-day solver with daily settlement times, lost demand rather than negative inventory, original paid orders retained, partial receipts excluded from future arrivals, unknown ETA excluded from certain arrivals, no forecast cash receipts, integer minor-unit cash, MOQ/pack/validity/quantity/budget/floor checks, at most three offers and 100 nonzero quantities per offer. An oversized search fails explicitly. v6 allocation uses the producer's persisted ceiling total and largest remainders with chronological ties.
- Golden synthetic result: stock 20, demand 10/day, original prepaid 50 on day 5, cash 800/floor 500/budget 300 selects B20 on day 3 for 240, lost demand 0 and ending stock 20. Budget 200 selects waiting with lost demand 20; buying cheap C20 later does not improve the objective.
- `RecoveryPlan`/`PlanDocument` extend read paths without altering baseline Plan or its canonical hash. Explicit selection is separate from default recommendation. Adoption creates only a pending Plan, preserves the Mission's long-term supplier policy, and records a one-time planning context. Current source/Case versions, solver output, selected supplier, cash and expiry are checked at adoption, approval and send. Existing role, store gate, Action, reservation, receipt and reconciliation paths remain authoritative.
- Ordinary Mission planning preserves a current pending recovery Plan. User revision supersedes an unapproved recovery Plan; queued old purchase intents become STALE before sending. UNKNOWN retains the original Action for reconciliation. An accepted purchase is not marked as delivered, partial delivery remains partial, and one Case cannot create a second accepted emergency purchase across revisions. A user may select C20 while B20 is recommended; the approved and sent supplier remains C despite identical quantities.
- Explicit `enable_followup`/`disable_followup` controls enable durable 30-second observations through the ordinary business worker. The new handler uses existing lease fencing and recovers missing jobs after restart; fingerprinted source/Action/inbound observations are deduplicated. Stale comparisons trigger `RECHECK_REQUIRED`. Closed/cancelled Cases stop scheduling. Elapsed business windows close with an unknown outcome when actual lost-demand evidence is absent; delivery is not treated as proof of goal success. Follow-up does not call a model or create a purchase.
- Optional advisory expert integration and Agent gateway access are delivered by the context workstream; see its separate report. Deterministic calculation is usable with the expert flag disabled.

## Runtime and migration

Migration `0015_operations_cases` follows `0014_forecast_work_merge`, adds four Case tables and nullable `missions.planning_context`. The normal business worker discovers `operations_case_followup` through `app/bootstrap.py`. No edits were made to the pre-existing dirty `scheduling/repository.py` or `scheduling/runner.py` in this workstream. No production/user database was migrated, no paid calls were made, and no commits were created.

The root's isolated PostgreSQL 17 harness uses a loopback server, `shopsteward_test`, and private connection material under ignored `var/next-phase-postgres`. Do not print the connection file or run these migration commands against a user database.

```powershell
.venv/Scripts/python.exe var/next-phase-tests/run.py backend -m pytest tests/integration/test_operations_cases.py tests/integration/test_planning_jobs.py tests/integration/test_execution.py tests/integration/test_missions.py -q -p no:cacheprovider --basetemp=../var/next-phase-tests/cases-pg-7 --tb=short
.venv/Scripts/python.exe var/next-phase-tests/run.py backend -m pytest tests/unit -q -p no:cacheprovider --basetemp=../var/next-phase-tests/cases-unit-final --tb=short
```

## Verification evidence

Tests were written and run before the associated production changes. The initial solver tests failed on the missing recovery module. Real-state regressions subsequently exposed an ignored Mission quantity ceiling, an unsuperseded purchase when adopting waiting, missing follow-up, stale historical Plan comparison after a new revision, and absent per-Case purchase limits; each was fixed after observing its failure.

- Initial related PostgreSQL suite: **42 passed**, including source-to-Plan-to-approval-to-supplier-receipt behavior and the baseline Mission/planning/execution regressions.
- Extended related suite: **44 passed, 2 failed**. Both failures were existing `test_execution::test_approval_rechecks_current_inputs` cases (`state-STATE_VERSION_CONFLICT` and `expiry-PLAN_EXPIRED`) obtaining an empty plan list while another workstream concurrently ran global queue fixtures. The workstreams confirmed the overlap and stopped parallel PostgreSQL suites. Sequential rerun of the complete execution module: **18 passed**.
- Follow-up/restart/new-revision tests passed in that extended run. Two later targeted PostgreSQL regressions for supplier selection and the one-accepted-purchase limit: **2 passed, 12 deselected**.
- Full backend unit suite after integration: **262 passed**. Scope includes the new golden solver/API-contract tests and existing baseline hash tests. No unit failures or skips in this run.
- Scoped Ruff from `backend/`: **all checks passed** for `app/operations_cases`, `app/planning/recovery` and the new Case/solver tests. Root owns final OpenAPI generation, frontend validation and the final sequential full repository integration run.

## Explicit boundaries

The implemented producer consumes authoritative structured business projections and explicit seven-day scenarios. It does not yet parse supplier PDF notices into a bounded applicability DSL, apply ETA/offer-change simulator events, or bind document versions as executable procurement parameters. Existing Knowledge permissions are not replaced by Case data. Cases currently attach to an existing Mission directly; automatic WorkItem intake/classification and canonical WorkItem-to-Case routing are separate consuming integration work.

There is no actual-lost-demand outcome oracle or automatic claim of RESOLVED. Unsupported hourly objectives, multi-SKU optimization, multiple emergency purchases, supplier negotiation and cancellation of already-sent orders remain outside this first seven-day model. Research accuracy/effectiveness and the formal CE48/OPS48 experiment are not established by these synthetic functional regressions.
