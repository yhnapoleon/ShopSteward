# Context, model protocol, and bounded Case experts — implementation record

Date: 2026-10-02. Scope: integrated-design sections 7–10, 13, 14, 19 and the context/runtime portion of implementation Task 1. Work stayed in the existing YH checkout; no commits or paid provider calls were made. Existing task-policy work was preserved. This report covers the context/runtime workstream; the root delivery report owns the final combined backend/frontend verification.

## What is connected to production paths

### Mission context and source admission

`agent_bridge.jobs` freezes a new run's context configuration in the existing Receipt store before starting the run. `context_sources.load_history` selects every admitted user message, successful earlier answers belonging to named prior runs, and explicit same-run resume messages. The old 80-message truncation is removed. Later queued user messages and their answers cannot enter an older run. A PostgreSQL worker test creates 163 admitted messages and a later queued message, and checks that the early budget survives while the later text is excluded.

`composition` passes these envelopes, the admission boundary, current knowledge/mission data, a frozen ModelProfile, and a durable call observer to the real Runtime. The ContextBuilder is invoked before actual model calls. Original user text remains in user-role messages, not promoted to system authority. Current application data is labelled separately. Required user sources are retained; optional earlier assistant turns are selected in complete groups under budget. Required overflow stops before model transmission with `context_required_overflow`.

The budget estimator is conservative UTF-8 JSON bytes with a 10% input safety margin. It is an estimate, not a provider tokenizer or billing claim. A small input limit may reject requests considerably earlier than the vendor's token limit.

### Executable TaskFrame scope

The live builder runs `context.frame.extract_frame`; this is not an unused DTO. Supported, source-checked constraints include:

- Chinese budget values in 元 or 分, converted to integer minor units.
- Quantity bounds expressed by 最多, 不超过, 至少, 恰好, 正好 and supported 数量上限/改成/改为/调整为 forms.
- Explicit cancellation of a budget or quantity bound; zero remains zero.
- Actual and hypothetical constraints separated by scope. A later supported correction replaces the same constraint without removing unrelated constraints. A hypothetical does not overwrite an actual constraint.

Each accepted constraint keeps the source message ID, exact quote and character span. Frame ID, source digest, parent frame ID, status and unresolved recognized commands are recorded. Unmatched wording is kept verbatim in the model request with `raw_fallback`; there is no claim of general natural-language semantic extraction. Historical preference commands are not reconstructed as current knowledge after their authoritative KnowledgeScope changes.

Mutation intent is one shared implementation in `context.intent.classify_intent`, used by the TaskFrame, the gateway and the older memory authorization helper. Explicit only-simulate/read/analyze and unqualified no-save instructions deny business writes. Targeted negatives only deny the relevant tools: “不要修改当前方案” denies plan/check mutation and still permits an explicit preference save; “不要保存这个偏好” denies memory; “不要下单” does not prohibit preparing a pending Plan. The Agent has no purchasing/approval tool. A later explicit “请把数量上限改成20件” or “Change the maximum to 20 items” supersedes the prior plan prohibition; a bare “20件” clarification preserves it.

Runtime validates proposed write arguments against the frame before invoking tools; the gateway independently checks admitted source intent, so a model cannot bypass the prohibition. The existing Mission `revise_plan` contract supports quantity upper bounds only. It cannot silently turn a budget, exact quantity or lower bound into `max_purchase_qty`; such recognized unsupported constraints fail explicitly. This frame does not add budget mutation to the existing Mission tool. Case budget and quantity decisions remain the deterministic recovery subsystem's responsibility.

### Active protocol and source invalidation

Within an active segment the Runtime preserves complete assistant/tool-call/tool-result protocol. Responses output items, including opaque encrypted reasoning, are replayed verbatim within that run. Incomplete provider responses do not execute tool calls. A safe model-call boundary can rebuild once if existing document authority is removed/changed, current knowledge changes or the mission goal changes. Derived older answers depending on unavailable documents are omitted with a reason, and stale active evidence/protocol is dropped at the segment boundary. Newly obtained document authority by itself does not discard the just-read evidence. A second invalidation stops with `context_changed`.

The rebuild includes operation names already attempted so a new segment can avoid duplicate writes, and required reads must be performed again. This is a bounded rebuild mechanism, not a complete semantic handoff/automatic compaction service. Business tool idempotency and version guards remain required.

### Model profiles and actual accounting

`OpenAIModel` preserves the existing `complete(messages, tools, tool_choice=...)` interface. Chat Completions uses the installed LangChain adapter; Responses uses the installed OpenAI SDK with `store=false`, explicit output cap, optional reasoning effort and `reasoning.encrypted_content`. Both transports apply configured reasoning effort. The Chat path has an actual HTTP MockTransport assertion for the outgoing `reasoning_effort` parameter. No live provider capability or model-availability claim was made.

The requested model ID is the configured value. The returned model and response ID are separate observed fields. Every transmitted call has a reserved record, followed by completed, failed or incomplete status when known. Input/output/total tokens and provider-reported cache/reasoning detail are retained per call. Missing or partial usage stays unknown; cumulative usage becomes unknown if any included call is unknown. No estimated price is reported: `cost_status` is always `unknown`. Provider SDK retries are disabled; Runtime repair calls consume normal budgets.

### Optional Case experts

`operations_cases.router.analyze` commits deterministic snapshot/solver analysis first, then optionally calls `attach_case_experts` outside that transaction. The default is disabled. The helper reads the authorized immutable revision snapshot and solver proposal, dispatches Evidence and Impact, and adds Options when multiple offers exist. These experts only read frozen evidence and produce advisory claims/missing inputs. Claim support must cite supplied or successful tool evidence IDs. Their text cannot modify candidate amounts, materialize/approve a Plan or execute a purchase.

The real `BoundedCaseRunner` uses the same Runtime and ContextBuilder. It permits one delegation depth, 1–3 experts, two simultaneous experts, local quotas and a shared ledger capped by default at 14 model calls, 28 tool calls and 150 seconds. Each expert has a maximum 60-second execution window and default 4 model/6 tool calls. A single explicit follow-up shares the same ledger; the product coordinator currently does not automatically dispatch that follow-up. The root Case coordinator is deterministic and does not itself make an LLM call.

Reservation and call accounting are persisted before provider sends. Repeated analyze calls for the same proposal/revision reuse the existing expert result instead of spending again. Revision/proposal/root-run identity, terminal Case status and live owner grants fence each new reservation and publication. Cancellation, changed inputs or permission revocation prevent subsequent calls; already-sent terminal records still enter the historical journal. Final response authorization is rechecked. PostgreSQL tests cover revision races, cancellation, grant revocation, replay and preservation of the historical ledger after the current projection is cleared.

## Integration interfaces and persisted records

Public owner-authorized inspection endpoint:

```text
GET /api/v1/agent-runs/{run_id}/context
operation_id: inspect_agent_context
{run_id, config: object|null, frames: object[], calls: object[], manifests: object[]}
```

`frames` currently contains the final/latest frame available in AgentRun.output. A running/failed run may have call manifests with no published final frame. `calls` can contain `reserved` with unknown usage; that is not evidence of a completed provider response. The endpoint never returns raw requests, API credentials or opaque reasoning. Authorized frame quotes can contain the user's own source text. Active protocol remains in the existing LangGraph checkpoint store.

Model call observer contract is `shopsteward_agent.context.contracts.CallRecord` (`schema_version=context-v1`): `run_id`, monotonic `call_index`, `segment_id`, `role`, `purpose`, `attempt`, `status`, `profile`, `manifest`, `request_hash`, `returned_model`, `response_id`, `usage`, `usage_status`, `cost_status`, `error_code`, `duration_ms`. Identity is `(run_id, role, call_index)` across reserved-to-terminal updates; `call_index` is not reset per segment. Current roles are `root`, `evidence`, `impact`, `options`; expert run IDs are root ID plus subtask ID. The offline rubric adapter consumes this explicit contract; business outcomes are separate trusted observations, not conclusions inferred from model prose.

Manifests contain source IDs/hashes, omission reasons, admission/profile/builder versions, frame ID, tools/request hashes and estimated input budget. These hashes identify selected inputs and requests; they are not proof that the provider used or correctly interpreted them.

Durable mapping reuses existing `Receipt` rows:

- `owner=context:<AgentRun.id>`, `key=config` freezes context/profile settings; `key=call:<role>:<index>` stores the latest reserved/terminal call record. Repeating a reservation for the same call is rejected, including an unknown interrupted outcome.
- `owner=case-context:<Case.id>:<revision>`, `key=<root_run_id>` stores expert budget, calls and result history. `CaseRow.expert_analysis` is only the current projection; revision/cancel can clear it without deleting the historical journal.

No new migration was added for this workstream. Namespaces are application mappings, not database foreign keys to AgentRun/Case or a dedicated normalized artifact/version table. There is no complete hard-deletion garbage collector for checkpoints or derived artifacts. Interrupted Case model graphs are marked partial/interrupted; the product helper does not transparently resume model execution. Unknown reservations are not treated as free retries.

Callable helpers:

```python
await analyze_case_experts(
    snapshot, case_id=..., revision_id=..., run_id=..., settings=...,
    proposal=..., persist=..., record_call=..., model=...,
)
await attach_case_experts(db, settings, principal, case_id, revision, proposal_id)
```

The injected `model` is for offline testing/integration; production requires explicit model configuration. Mission tools `get_recovery_cases`, `get_recovery_case`, and `analyze_recovery_case` are wired to owner/store/Mission-scoped Case repositories. The analysis tool invokes only deterministic analysis, so it cannot recursively trigger the paid expert hook. Plan comparison now parses both existing Plans and recovery Plans and projects recovery candidates into the existing comparison DTO.

## Configuration

Settings/environment names are case-insensitive and read through the existing Settings loader:

| Setting / environment variable | Default | Meaning |
| --- | --- | --- |
| `agent_context_enabled` / `AGENT_CONTEXT_ENABLED` | `true` | Enable context building for new eligible Mission runs. |
| `agent_profile_id` / `AGENT_PROFILE_ID` | `mission-configured` | Auditable requested profile label. |
| `agent_model` / `AGENT_MODEL` | existing `gpt-4.1-mini` | Requested Mission model; no silent replacement. |
| `agent_api_mode` / `AGENT_API_MODE` | existing `chat_completions` | Explicit transport. |
| `agent_reasoning_effort` / `AGENT_REASONING_EFFORT` | unset | Sent only when configured; operator must choose a supported model/value. |
| `agent_max_input_tokens` / `AGENT_MAX_INPUT_TOKENS` | `24000` | Conservative input admission cap for both Mission and Case. Case does not raise a smaller configured cap. |
| `agent_max_output_tokens` / `AGENT_MAX_OUTPUT_TOKENS` | `2048` | Explicit provider output limit. |
| `agent_model_timeout_seconds` / `AGENT_MODEL_TIMEOUT_SECONDS` | `30` | Per-model timeout. |
| `agent_case_experts_enabled` / `AGENT_CASE_EXPERTS_ENABLED` | `false` | Enable optional advisory expert hook after deterministic analysis. |
| `agent_case_model` / `AGENT_CASE_MODEL` | unset | Must explicitly name the Case model. |
| `agent_case_api_mode` / `AGENT_CASE_API_MODE` | `responses` | Explicit Case transport. |

Existing `AGENT_BASE_URL` and `AGENT_API_KEY_FILE` supply the endpoint and a private key file. Do not put secrets in profile DTOs or inspector data. Case experts return `unavailable` with `CASE_MODEL_NOT_CONFIGURED` without sending when enabled but no production model/key file is configured. Test fixtures use injected models and larger explicit input limits where their full solver documents require it.

New queued runs freeze their own configuration; changing environment settings does not rewrite an already-frozen run. Existing legacy runs can retain their old graph path. The context-enabled flag controls the Runtime context builder; backend source admission and mutation authorization are still enforced.

## Verification record

All provider behavior was tested with fakes or HTTP MockTransport. PostgreSQL used the parent-created dedicated PostgreSQL 17.11 instance on loopback port 55434, migrated through 0015. The wrapper reads private connection configuration without printing credentials. Database suites must run sequentially: existing global cleanup fixtures delete/claim shared queue rows.

Final workstream commands, run from the repository root:

```powershell
uv run --package shopsteward-backend --extra agent pytest agent/tests -q -p no:cacheprovider
# 93 passed, 3 skipped in 3.37s (the three tests require PostgreSQL).

uv run --package shopsteward-backend --extra agent pytest backend/tests/unit/test_agent_presentation.py backend/tests/unit/test_case_experts.py backend/tests/unit/test_context_admission_unit.py -q -p no:cacheprovider
# 16 passed in 1.96s.

.venv/Scripts/python.exe var/next-phase-tests/run.py backend -m pytest tests/integration/test_agent_context.py tests/integration/test_case_expert_context.py tests/integration/test_agent_tools.py -q --basetemp=../var/next-phase-tests/context-last-pg --tb=short -p no:cacheprovider
# 11 passed in 11.44s. Final combined backend verification belongs to the root run.
```

Earlier database-backed Agent full regression: 82 passed in 6.32s, before the final targeted intent additions. Earlier backend Agent/integration selection: 52 passed, 2 browser-opt-in skipped, 215 deselected in 35.15s. These earlier counts are supplementary, not substitutes for the root's final combined run.

Test-first failures were observed before fixes for missing context/case implementations, live runtime wiring, recovery Plan parsing, frame correction/scenario separation, historical expert accounting, spurious source invalidation, missing Chat reasoning effort, adversarial no-save writes and targeted positive authorization. The last review fix reproduced three memory/plan target false positives and a real gateway `EXPLICIT_MEMORY_INTENT_REQUIRED` failure before using the shared classifier; the Case budget regression observed two model sends despite a configured 256-token cap before the cap was corrected. The corrected Case test now sends zero model calls and reports overflow.

Verification issues were not product failures hidden from the result: an initial root full-backend collection failed because newly added unit and integration files shared `test_agent_context.py`; the unit file is now `test_context_admission_unit.py`. One mixed-root pytest invocation lacked the backend import path and failed collection; separate project commands passed. Earlier simultaneous database suites interfered through global queue fixtures; sequential execution regressions passed afterward. The final 11-test workstream run briefly overlapped the root's first final attempt due coordination error, so root owns a fresh full-backend run. No more workstream database runs were started after handoff.

Latest read-only scoped Ruff check found only formatting/import issues in the new `tools.py` guard and `agent/tests/test_runtime.py` test imports; they were communicated to root during the implementation freeze for final formatting/verification. Do not interpret this report as claiming a clean final repository-wide lint run.

## Files in this workstream

- Agent: `context/{contracts,builder,frame,intent,__init__}.py`, `cases/{budget,runner,__init__}.py`, `model.py`, `runtime.py`.
- Backend: `agent_bridge/context_{sources,repository,router,cases}.py`, `composition.py`, `jobs.py`, `tools.py`, `outcomes.py`, and the small shared memory-denial change in `presentation.py`.
- Coordinated integration edits: Agent settings in `core/config.py`, context router registration in `main.py`, post-commit optional expert hook in `operations_cases/router.py`.
- Tests: `agent/tests/test_{context,cases,model_protocol,runtime}.py`; backend unit `test_context_admission_unit.py`, `test_case_experts.py`, `test_agent_recovery_compat.py`, `test_agent_presentation.py`; backend integration `test_agent_context.py`, `test_case_expert_context.py`, plus targeted positive authorization in `test_agent_tools.py`.

## Explicit remaining boundaries

There is no general semantic constraint extractor, model-generated summarizer, automatic Case follow-up coordinator or checkpoint/artifact deletion service. The Case product helper exposes frozen snapshot, forecast profile, offers and solver evidence; the role whitelist contains future document-read capabilities, but this helper does not perform external document retrieval. Citation IDs validate provenance availability, not semantic entailment; offline semantic/business evaluation must supply its own typed observations. Provider capability flags are descriptive and no live E0/model capability probe was run. There is no measured token saving, cost saving or quality uplift claim. Monetary cost remains unknown until a separately versioned price contract and complete measured usage are available.
