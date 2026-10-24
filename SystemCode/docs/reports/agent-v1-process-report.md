# Agent v1 real process acceptance

Final evidence: three focused knowledge cycles and the recovery suite passed. The preceding full baseline passed all non-memory checks; its knowledge failure and every earlier failed attempt remain in the JSON report.

| Scope | Verified result |
|---|---|
| Real-model knowledge | 3 independent synthetic stores, 24 Runs, 51 checks; USER and SKILL save/read/correct/delete, versions 1 → 2 → 3, new conversations read the current plan |
| Core plan baseline | 3 real-model explanations with authoritative 40-unit recommendation and 80-unit rejection cards |
| What-if / revision baseline | Hypothetical max20 leaves mission unchanged; explicit max20 produces a new pending plan |
| Followup baseline | Independent background Run, actual 65-second unchanged window without repeated Run, stock event then another background Run (due timestamp controlled) |
| Abrupt worker kill | Observed RUNNING, killed owned worker, waited 14 seconds, restarted; job attempt 2 succeeded with exactly one assistant message |
| Two workers | Two independent workers served two messages in one conversation; each Run published exactly one assistant message |
| Cancellation | Cancelled observed RUNNING; persisted CANCELLED and zero assistant messages |
| Clarification | Model invoked clarify on an explicit synthetic clarification request; WAITING_INPUT resumed in the same Run and published one assistant message |

All six fresh-conversation read replies from the latest three focused cycles were manually reviewed: USER conclusion plus three reasons, SKILL cash floor before candidate explanation, and correct monetary values; no fallback warnings in those six replies.

The full baseline ran before the final read-intent classifier fix. The three subsequent focused cycles validate knowledge after that fix; non-memory full scenarios were not needlessly repeated. Runtime success alone is not treated as proof of narrative correctness.

Not fault-injected: memory transaction commit followed by lost HTTP response; other adversarial scenarios beyond the listed process checks. Cancellation and worker recovery use genuine owned processes and normal user APIs, with no production fault endpoints.

Model: `gpt-4.1-mini`; official endpoint: `https://api.openai.com/v1`; isolated retained database: `shopsteward_agent_acceptance`; schema `0009_agent_scopes`.
Cumulative reported token usage: 392667; 2 Runs have unavailable usage, so this is not a complete spend total.

All owned processes were stopped. Existing services on ports 8000/8001 were not stopped. Synthetic stores and durable Runs remain available for review. Detailed prompts, run IDs, cards, usage, snapshots, and retained failures are in `docs/api/agent-v1-process-result.json`.
