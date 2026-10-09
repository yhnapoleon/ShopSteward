"""Offline evolution of the Case text bundle with GEPA.

Runs only in the separate optimizer environment. The optimizer reads feedback
from the training partition and scores from the validation partition; it never
sees the gate partition. Its output is a new bundle revision, which is enabled
only by configuration after the gate comparison.
"""

import asyncio
import json
from pathlib import Path

from . import _paths  # noqa: F401
from .runner import run_one

MAX_COMPONENT_CHARS = 1500
# GEPA's default reflection prompt asks for long, self-contained instructions and
# invites the model to restate the output format. Here the format, tools and safety
# rules are fixed in code, so the prompt asks only for a short, better question.
REFLECTION_TEMPLATE = """One read-only expert in a retail supply-recovery analysis system is given the \
question below. It is the only part of the expert's prompt you may change. The output format, \
the typed-claim vocabulary, the tools and the safety rules are fixed elsewhere and must not be \
restated or changed.
```
<curr_param>
```

These are runs on different cases: what the expert produced, and feedback from an automatic \
checker that compares the typed claims with the solver output.
```
<side_info>
```

Write an improved question for this expert. Keep the expert's purpose. Add only what the \
feedback shows is needed, in plain sentences. Do not define an output schema, do not mention \
specific cases, and stay under 1200 characters.

Provide the new question within ``` blocks."""


def feedback(record):
    """Plain-language account of one training run; this is what the reflection model reads."""
    lines = [f"Score {record['score']:.2f} (0 means failed or contradicted the solver)."]
    missing = [item for item in record["required"] if item not in record["covered"]]
    if missing:
        lines.append(
            "Required typed claims that were not stated (format type:candidate_id=result): "
            + ", ".join(missing)
            + "."
        )
    if record["contradictions"]:
        lines.append(
            "Typed claims that contradict the solver output: "
            + ", ".join(record["contradictions"])
            + ". Every typed claim must restate a solver field exactly."
        )
    if record["failed_subtasks"]:
        lines.append("Failed subtasks: " + json.dumps(record["failed_subtasks"]) + ".")
    if "unnecessary_clarification" in record["critical_failures"]:
        lines.append(
            "The run asked the user a question although every needed fact was supplied; "
            "missing documents should be reported in `missing`, not asked for."
        )
    if record["unverifiable"]:
        lines.append(f"{record['unverifiable']} typed claims used results outside the vocabulary.")
    lines.append(
        f"Cost: {record['model_calls']} model calls, {record['tool_calls']} tool calls, "
        f"{record['claim_count']} claims in the joined result, follow-up {record['followup']}."
    )
    return " ".join(lines)


class CaseBundleAdapter:
    """GEPAAdapter over frozen cases. One metric call is one strategy run on one case."""

    propose_new_texts = None

    def __init__(self, *, base, strategy, model, profile, parallel=3):
        self.base, self.strategy, self.model, self.profile = base, strategy, model, profile
        self.parallel = parallel
        self.loop = asyncio.new_event_loop()  # one loop keeps the HTTP client reusable
        self.log, self.reflections = [], []
        self.retry_waits = (10, 30)

    def bundle(self, candidate):
        from shopsteward_agent.cases import make_bundle
        from shopsteward_agent.context.contracts import digest

        return make_bundle(
            "candidate-" + digest(candidate)[:12],
            {**self.base.components, **candidate},
            parent_revision=self.base.revision,
        )

    def evaluate(self, batch, candidate, capture_traces=False):
        from gepa import EvaluationBatch

        oversized = [k for k, text in candidate.items() if len(text) > MAX_COMPONENT_CHARS]
        bundle = None if oversized else self.bundle(candidate)
        gate = asyncio.Semaphore(self.parallel)

        async def one(pair):
            if bundle is None:
                return None
            async with gate:
                for wait in (*self.retry_waits, None):
                    try:
                        item = await run_one(
                            *pair,
                            strategy=self.strategy,
                            bundle=bundle,
                            model=self.model,
                            profile=self.profile,
                        )
                    except Exception as exc:  # one bad example must not abort the search
                        return exc
                    if not item["record"]["provider_error"]:
                        return item
                    if wait is None:
                        # Scoring an outage as 0 would poison the search; stop instead.
                        raise RuntimeError("model provider unavailable; rerun to resume")
                    await asyncio.sleep(wait)

        async def many():
            return await asyncio.gather(*(one(pair) for pair in batch))

        outputs, scores, trajectories, objectives = [], [], [], []
        for (case, _), item in zip(batch, self.loop.run_until_complete(many()), strict=True):
            if item is None or isinstance(item, Exception):
                reason = (
                    f"Component over {MAX_COMPONENT_CHARS} characters: {oversized}"
                    if item is None
                    else f"Run error: {type(item).__name__}"
                )
                record = {"case_id": case.case_id, "score": 0.0, "error": reason}
                trajectory = {"record": record, "subtasks": [], "feedback": reason}
                frugality = 0.0
            else:
                record = {
                    **item["record"],
                    "claim_count": len(item["analysis"]["merged"]["claims"]),
                }
                trajectory = {
                    "record": record,
                    "subtasks": item["analysis"]["subtasks"],
                    "feedback": feedback(record),
                }
                frugality = 1 - record["model_calls"] / 14
            outputs.append(record)
            scores.append(record["score"])
            trajectories.append(trajectory)
            objectives.append({"quality": record["score"], "frugality": frugality})
        self.log.append(
            {
                "bundle": bundle.content_hash if bundle else None,
                "cases": [case.case_id for case, _ in batch],
                "scores": scores,
                "notes": [
                    output.get("error")
                    or ", ".join(
                        [
                            *output["critical_failures"],
                            *(c for v in output["failed_subtasks"].values() for c in v),
                        ]
                    )
                    for output in outputs
                ],
            }
        )
        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories if capture_traces else None,
            objective_scores=objectives,
            num_metric_calls=len(batch),
        )

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        dataset = {}
        for component in components_to_update:
            role = component.split(".", 1)[1]
            rows = []
            for trajectory in eval_batch.trajectories:
                # A root strategy answers all three questions in one subtask.
                mine = [
                    task
                    for task in trajectory["subtasks"]
                    if task["role"] in (role, "single", "fixed")
                ]
                typed = [
                    f"{c['subject'].get('type')}:{c['subject'].get('id')}="
                    f"{(c.get('applicability') or {}).get('result')}"
                    for task in mine
                    for c in task["claims"]
                    if c.get("subject")
                ]
                rows.append(
                    {
                        "Inputs": "A frozen business snapshot and solver proposal for one case.",
                        "Generated Outputs": {
                            "status": [task["status"] for task in mine],
                            "claims": sum(len(task["claims"]) for task in mine),
                            "typed_claims": typed,
                            "missing": [item for task in mine for item in task["missing"]][:5],
                            "followup_requests": sum(
                                len(task["followup_requests"]) for task in mine
                            ),
                        },
                        "Feedback": trajectory["feedback"],
                    }
                )
            dataset[component] = rows
        return dataset


def evolve(
    pairs,
    *,
    base,
    strategy,
    task_model,
    task_profile,
    reflection_model,
    components,
    max_metric_calls,
    run_dir,
    seed=0,
    minibatch=3,
    parallel=3,
):
    """Return (best components, GEPA result, adapter). Callers decide whether to release."""
    import gepa

    adapter = CaseBundleAdapter(
        base=base, strategy=strategy, model=task_model, profile=task_profile, parallel=parallel
    )

    def reflect(prompt):
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        reply = adapter.loop.run_until_complete(reflection_model.complete(messages, []))
        adapter.reflections.append(reply["content"])
        return reply["content"]

    if any(pair[1]["partition"] not in ("evo-train", "evo-val") for pair in pairs):
        raise ValueError("only evo-train and evo-val cases may be given to the optimizer")
    train = [pair for pair in pairs if pair[1]["partition"] == "evo-train"]
    val = [pair for pair in pairs if pair[1]["partition"] == "evo-val"]
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    result = gepa.optimize(
        seed_candidate={name: base.components[name] for name in components},
        trainset=train,
        valset=val,
        adapter=adapter,
        reflection_lm=reflect,
        reflection_minibatch_size=minibatch,
        max_metric_calls=max_metric_calls,
        run_dir=str(run_dir),
        seed=seed,
        reflection_prompt_template=REFLECTION_TEMPLATE,
        display_progress_bar=False,
        raise_on_exception=True,
    )
    return result.best_candidate, result, adapter
