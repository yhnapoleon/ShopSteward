# Implementation ledger — plan: docs/superpowers/plans/2026-10-03-memory-skill-workflow-evolution-plan.md

Started 2026-10-03. First delivery P0–P2; workflow/A2UI remain subsequent stages.
Baseline YH / 30bed9f with pre-existing uncommitted next-phase implementation.
Ruling: Work in the specified current checkout, preserving existing changes — required interfaces exist only in that working tree; do not make a commit that mixes other work.
Ruling: Per-user consent defaults off; the global feature flag defaults false. Setting suggest explicitly starts collection from that point; no silent historic backfill.
Ruling: Human calibration cannot be fabricated. Automatic activation remains gated on independent verified evaluation; implement the gate and mark absent evidence unknown.
Pre-flight: Task 2 outbox -> Task 3 collector -> Task 4 candidates share server-derived scope and immutable evidence.
Pre-flight: Task 5 activation depends on Task 7a exact revision-bound report before Task 6 retrieval.
Pre-flight: Task 8 uses matured outcome revisions, never Agent SUCCEEDED as business success.

Verified: foundation contracts/policies/rubric 17 tests; transactional storage 3 tests; API lifecycle/case capture 3 tests; extraction 3 agent tests; generation worker 1 test.
Verified: admission, preference invalidation, source tombstones and late receipt preservation 4 integration tests; paired metrics/applicability 3 unit tests; review disagreement 1 unit test.
Verified: first backend regression 578 passed / 3 skipped; frontend typecheck and production build passed; learning browser tests 3 passed (real Vue, intercepted transport).
Ruling: Scope of the first executable delivery is the skill vertical slice. Workflow DSL/A2UI remain later work. Whole-system temporal ablation and human calibration are not represented as completed experiments; cost if deferred: no evidence yet of real operating benefit.
Ruling: Reuse the existing checkout without commits, so unrelated uncommitted changes are preserved; cost: review must use the listed feature files rather than a clean branch diff.
Ruling: Explicit memory changes conservatively invalidate all inferred skills in the same scope and reset the consent evidence epoch; cost: more relearning than a future fine-grained dependency graph.
Ruling: Offline evaluation uses a trusted maintainer CLI, frozen campaign manifest, checksum-bound replay artifacts and two human reviews. No public or Agent tool accepts self-awarded release scores; cost: human work is required before activation.
Ruling: Wilson bounds for paired gain/loss frequencies conservatively replace the unspecified confidence-interval estimator. Twenty cases are coverage only, not sufficient proof of noninferiority; cost: low-frequency skills may remain candidates much longer.
Environment: pnpm's newer global executable attempted an implicit install and wrote an esbuild placeholder. Removed only that generated placeholder; used already-installed Nuxt/Playwright CLIs directly. Dependency versions and script approval settings unchanged.
Final review: independent read-only reviewer (gpt-6-astra), seven Important findings, no Critical or Minor findings. Fix pass accepted all seven.
Final: fixed real goods receipt capture — test_real_goods_update_outcomes_and_replay_once RED→GREEN.
Final: fixed in-flight revocation at tool/publication transactions — test_revocation_during_model_call_blocks_tool_and_final_publication RED→GREEN.
Final: fixed static recheck overwriting active admission — test_static_recheck_does_not_replace_active_release_report RED→GREEN.
Final: fixed per-Run version and empty-selection pinning — test_run_pins_revision_and_empty_selection_across_publication RED→GREEN.
Final: fixed cancellation tombstone and real control normalization — test_cancelled_episode_cannot_be_revived_by_late_receipt and test_mission_owner_stays_creator_and_real_cancel_removes_eligibility RED→GREEN.
Final: fixed stable Mission owner (actor is only provenance) — owner/control integration test RED→GREEN.
Final: fixed inherited result availability under out-of-order consumption — test_inherited_outcome_never_predates_its_evidence RED→GREEN.
Final review fix suite: 7/7 passed; explicit-memory continuation test also passed. All fixes are covered by the final whole-backend run below.
Final: Ruling: Reviewer set aside Workflow DSL/A2UI — remains explicitly subsequent scope, so no claim of implementation; cost: route/UI self-evolution still unavailable.
Final: Ruling: Reviewer set aside real-model benefits, human calibration and temporal ablation — documented as unmeasured, not passing; cost: cannot claim verified real-world gain.
Final: Ruling: Reviewer set aside unrelated pre-existing changes — preserve them and run shared regression; cost: this review does not certify those changes independently.

## Final verification

- Backend full suite: **644 passed, 3 skipped**, `var/evolution-tests/backend-release.log` (232.69s). Includes real isolated PostgreSQL, API contracts, all learning integration tests and existing business regressions. Skips remain unexecuted, not counted as pass.
- Agent full suite: **128 passed**, `var/evolution-tests/agent-final.log`. Includes optional-learning budget fallback preserving explicit user constraints.
- Browser: **22 passed**, `var/evolution-tests/browser-final.log`; real production Vue build with controlled transport fixtures across learning, task workspace and recovery. These are not live model/procurement experiments.
- Nuxt production build and typecheck passed; generated OpenAPI/TypeScript/proxy contract check passed. Relevant Python Ruff and `git diff --check` passed (existing CRLF normalization notices only).
- Migration `0016 → 0015 → 0016` verified twice on isolated test databases, including after readable static-DDL formatting. No daily-use database migrated.
- Trusted evaluation CLI imports and `--help` verified; successful report registration exercised by synthetic integration fixtures. No synthetic score was registered into the daily-use database or presented as measured model quality.
- Temporary frontend server and isolated PostgreSQL started for this verification are stopped after completion; test data/logs remain under ignored `var/evolution-tests` and `var/next-phase-postgres`.

Current delivery status: executable Skill learning vertical slice plus monitoring/evaluation foundations. Complete P2 research calibration, automated business replay adapter, scheduled re-evaluation, Workflow DSL, A2UI and cross-asset evolution remain explicitly pending in the plan. No automatic activation of unmeasured candidates.

