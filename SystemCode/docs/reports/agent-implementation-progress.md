# Agent implementation ledger

Plan: docs/superpowers/plans/2026-09-07-agent-framework.md

User authorized implementation on 2026-09-07, including task Skills and conversational what-if/revision loop.

Ruling: work in the existing YH checkout, preserve all existing changes, no commit/push. This is the user's active shared workspace; no destructive isolation/migration of their work.

Ruling: USER memory holds general preferences; versioned task Skills hold task procedures/preferences. A one-off constraint stays on a proposal. Formal approvals remain existing user APIs.

Ruling: A0/A2/A3 form an independently owned runtime package; backend integration is owned by coordinator. Agent imports no backend code. Execution uses injected callbacks and fenced checkpoint writes.

Interface review: A1/A2 share Run identity and recovery mode; A2/A3 share serializable graph state and injected runtime; A3/A4 share tool schema/call protocol; A4/A5 share authenticated tool receipts; A5/A7 share versioned memory and skill context; A1/A6 share conversation lock and active slot; A6/A8 share persistent trigger watermark; A7/A8 share actual API export. Implement and test these at boundaries.

Status: first framework implementation and scoped acceptance completed. See [test report](agent-v1-test-report.md) for the current evidence and remaining original-plan items.

Delivered A0–A7 core: installable runtime, actual StateGraph, fenced official PG checkpoints, owner-scoped conversations and FIFO Runs, independent Agent worker, bounded authenticated tools, explicit versioned USER/NOTES/SKILL edits, event watermark followup, actual API contracts and extension seams. A8 core scenarios passed; the full originally proposed process fault matrix and semantic summary remain unimplemented, as recorded in the plan addendum.

Runtime and backend reviews identified actionable protocol, resume replay, memory-write intent and lock-order issues. Coordinator inspected the code and regression evidence, fixed the Conversation FK lock cycle, protected old interrupt replay, required successful memory tool receipts, and rejected explicit denial during memory clarification. The last denial regression was first observed failing, then passed after the fix.

Final automated evidence: backend + agent 226 passed / no skips; simulator 12 passed / no skips. Ruff, formatting, Alembic drift, API contract checks, exact API key absence scan and wheel/sdist build passed. Real-model evidence: three knowledge cycles (51 checks, 24 Runs), prior 14 non-memory checks, 7 recovery checks. Prior failures remain in the process evidence rather than being erased.

Environment: only dedicated test/acceptance databases migrated to 0009_agent_scopes. Original development database and 8000/8001 services preserved. Owned 8024 API/worker processes stopped. No Git commit, push or branch change performed.
