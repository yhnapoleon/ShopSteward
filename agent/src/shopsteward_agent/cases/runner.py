"""Depth-one, read-only experts using the same Runtime, context and ledger."""

import asyncio
import json
import time
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from ..context import AdmissionBoundary, ContextBuilder, MessageEnvelope
from ..context.contracts import Contract, digest
from ..runtime import Runtime, RuntimeFailure

ROLE_TOOLS = {
    "evidence": {
        "read_case_snapshot",
        "search_documents",
        "read_document_evidence",
        "read_notice_versions",
        "resolve_entities",
    },
    "impact": {"read_case_snapshot", "read_forecast_profile", "simulate_recovery"},
    "options": {
        "read_case_snapshot",
        "list_case_offers",
        "read_document_evidence",
        "evaluate_recovery",
    },
}
EXPERTS = tuple(ROLE_TOOLS)
# Root strategies reuse the expert contract so every strategy is scored alike:
# the single agent sees every expert tool, the fixed workflow none.
ROLE_TOOLS["single"] = set().union(*ROLE_TOOLS.values())
ROLE_TOOLS["fixed"] = set()
CLAIM_KINDS = ("source_fact", "interpretation", "assumption", "calculation")


def _parse(content):
    """Chat models often fence the object or add a sentence; accept one embedded object.

    The object itself is still validated strictly by the caller.
    """
    start, end = content.find("{"), content.rfind("}")
    try:
        return json.loads(content[start : end + 1])
    except ValueError:
        raise ValueError("invalid_subtask_result") from None


def _request_ok(item):
    return isinstance(item, str) or (
        isinstance(item, dict)
        and set(item) <= {"role", "question"}
        and isinstance(item.get("question"), str)
        and item.get("role", EXPERTS[0]) in EXPERTS
    )


class SubtaskSpec(Contract):
    case_id: str
    revision_id: str
    run_id: str
    subtask_id: str
    role: Literal["evidence", "impact", "options", "single", "fixed"]
    question: str
    allowed_scope: dict[str, str]
    snapshot_id: str | None = None
    supplied_evidence_ids: list[str] = Field(default_factory=list)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    # Upper bounds are the root ledger's; only a root strategy asks for that much.
    max_model_calls: int = Field(default=4, ge=1, le=14)
    max_tool_calls: int = Field(default=6, ge=1, le=28)


class BoundedCaseRunner:
    def __init__(
        self,
        *,
        model,
        profile,
        tools,
        call_tool,
        budget,
        record_call=None,
        checkpointer_factory=None,
        role_models=None,
    ):
        self.model, self.profile, self.tools, self.call_tool = model, profile, tools, call_tool
        self.budget, self.record_call = budget, record_call
        self.checkpointer_factory = checkpointer_factory or InMemorySaver
        # role -> (model, profile), frozen for the run; other roles use the default.
        self.role_models = dict(role_models or {})
        self.semaphore = asyncio.Semaphore(2)
        self.followups = 0
        self.specs = {}

    def assigned(self, role):
        return self.role_models.get(role, (self.model, self.profile))

    async def _one(self, spec):
        async with self.semaphore:
            run_id = f"{spec.run_id}:{spec.subtask_id}"
            model, profile = self.assigned(spec.role)
            remaining = self.budget.deadline - time.time()
            # Experts get a bounded slice; a root strategy may use the root window.
            window = min(60, remaining) if spec.role in EXPERTS else remaining
            tools = [
                tool for tool in self.tools if tool["function"]["name"] in ROLE_TOOLS[spec.role]
            ]
            allowed_names = {tool["function"]["name"] for tool in tools}

            async def call_tool(name, args, invocation_id):
                if name not in allowed_names or self.call_tool is None:
                    raise RuntimeFailure("unknown_tool")
                return await self.call_tool(spec, name, args, invocation_id)

            async def context():
                return json.dumps(
                    {
                        "role": spec.role,
                        "scope": spec.allowed_scope,
                        "dependency_versions": spec.dependency_versions,
                        "evidence_ids": spec.supplied_evidence_ids,
                        "data": spec.context,
                        "output_contract": "Return one JSON object with claims [{statement, support:[evidence_id], kind?, subject?, applicability?:{result}}], missing:[], followup_requests:[string | {role, question}]. kind is source_fact, interpretation, assumption or calculation; a calculation claim must cite the solver proposal ID. Give subject and applicability.result when judging whether a source applies to an object. Two typed claims are checked against the solver output: subject {type:'candidate', id:<solver candidate id>} with applicability.result recommended, feasible or rejected (rejected means the solver lists rejection reasons for it, feasible means it lists none, recommended is the solver's recommended_candidate_id); and subject {type:'gap', id:<solver candidate id>} with applicability.result none or day-N, where N is the 1-based position of the first entry in that candidate's daily list with lost_qty above zero. A follow-up role is evidence, impact or options. Use only supplied or successful tool evidence IDs. All claims are advisory; no purchasing approval or memory/plan writes.",
                    },
                    ensure_ascii=False,
                )

            runtime = Runtime(
                model,
                self.checkpointer_factory(),
                tools,
                call_tool,
                context,
                context_builder=ContextBuilder(profile),
                admission=AdmissionBoundary(
                    kind="case",
                    run_id=run_id,
                    case_id=spec.case_id,
                    input_revision=int(spec.revision_id) if spec.revision_id.isdigit() else None,
                    input_through_seq=1,
                ),
                message_envelopes=[
                    MessageEnvelope(
                        message_id=spec.subtask_id,
                        run_id=run_id,
                        seq=1,
                        role="user",
                        content=spec.question,
                    )
                ],
                max_model_calls=spec.max_model_calls,
                max_tool_calls=spec.max_tool_calls,
                run_timeout=max(0.001, window),
                model_timeout=profile.timeout_s,
                shared_budget=self.budget,
                role=spec.role,
                record_call=self.record_call,
            )
            base = {
                "subtask_id": spec.subtask_id,
                "role": spec.role,
                "revision_id": spec.revision_id,
                "dependency_hash": digest(spec.dependency_versions),
                "claims": [],
                "missing": [],
                "followup_requests": [],
            }
            answer, unsupplied = None, None
            try:
                result = await runtime.execute(run_id, [{"role": "user", "content": spec.question}])
                if result["status"] == "WAITING_INPUT":
                    return {**base, "status": "needs_input", "missing": [result["question"]]}
                answer = result["content"]
                parsed = _parse(answer)
                if not isinstance(parsed, dict) or set(parsed) - {
                    "claims",
                    "missing",
                    "followup_requests",
                }:
                    raise ValueError("invalid_subtask_result")
                claims = parsed.get("claims", [])
                missing = parsed.get("missing", [])
                followup = parsed.get("followup_requests", [])
                if (
                    not isinstance(claims, list)
                    or not all(isinstance(item, str) for item in missing)
                    or not isinstance(followup, list)
                    or not all(_request_ok(item) for item in followup)
                ):
                    raise ValueError("invalid_subtask_result")
                evidence = set(spec.supplied_evidence_ids) | {
                    ref.get("id") for ref in result["references"] if isinstance(ref, dict)
                }
                for claim in claims:
                    if (
                        not isinstance(claim, dict)
                        or not isinstance(claim.get("statement"), str)
                        or not isinstance(claim.get("support"), list)
                        or not claim["support"]
                        or not all(
                            isinstance(ref, str) and ref in evidence for ref in claim["support"]
                        )
                    ):
                        support = claim.get("support") if isinstance(claim, dict) else None
                        unsupplied = [
                            str(ref)
                            for ref in (support if isinstance(support, list) else [])
                            if not (isinstance(ref, str) and ref in evidence)
                        ]
                        raise ValueError("unsupported_claim")
                    # Typed metadata drives the code-side join; unknown values fail closed.
                    if (
                        claim.get("kind", "interpretation") not in CLAIM_KINDS
                        or not isinstance(claim.get("subject", {}), dict)
                        or not isinstance(claim.get("applicability", {}), dict)
                    ):
                        raise ValueError("invalid_subtask_result")
                return {
                    **base,
                    "status": "partial" if missing else "complete",
                    "claims": claims,
                    "missing": missing,
                    "followup_requests": followup,
                    "context_manifest": result["context_manifest"],
                }
            except (RuntimeFailure, ValueError) as exc:
                failed = {
                    **base,
                    "status": "failed",
                    "missing": [exc.code if isinstance(exc, RuntimeFailure) else str(exc)],
                }
                if answer is not None:
                    # Kept as written: a rejection that cannot be read back cannot be diagnosed.
                    failed["rejected"] = {"answer": answer[:4000], "unsupplied": unsupplied or []}
                return failed

    async def run(self, specs, *, depth=0):
        specs = [SubtaskSpec.model_validate(spec) for spec in specs]
        if depth != 0 or not 1 <= len(specs) <= 3 or self.specs:
            raise ValueError("delegation_limit")
        identity = {
            (spec.case_id, spec.revision_id, spec.run_id, digest(spec.allowed_scope))
            for spec in specs
        }
        if len(identity) != 1 or len({spec.subtask_id for spec in specs}) != len(specs):
            raise ValueError("subtask_scope_mismatch")
        self.specs = {spec.subtask_id: spec for spec in specs}
        subtasks = await asyncio.gather(*(self._one(spec) for spec in specs))
        snapshot = self.budget.snapshot()
        return {
            "status": "complete"
            if all(item["status"] == "complete" for item in subtasks)
            else "partial",
            "subtasks": subtasks,
            "budget": snapshot,
            "usage": snapshot["usage"],
            "cost_status": "unknown",
        }

    async def followup(self, subtask_id, question, *, role=None):
        original = self.specs.get(subtask_id)
        if self.followups >= 1 or original is None or original.role not in EXPERTS:
            raise ValueError("followup_limit")
        role = role or original.role
        if role != original.role:
            # The one follow-up may instead start an expert this root has not used.
            if role not in EXPERTS or role in {spec.role for spec in self.specs.values()}:
                raise ValueError("followup_limit")
            subtask_id = role
        self.followups += 1
        # Same source boundary, one new segment; global quota is unchanged.
        return await self._one(
            original.model_copy(
                update={"subtask_id": subtask_id + ":followup", "role": role, "question": question}
            )
        )
