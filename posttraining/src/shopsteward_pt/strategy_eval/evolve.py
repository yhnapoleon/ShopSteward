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
            bundle_id=self.base.bundle_id,
        )

    # What one example is; a subclass over other data replaces these four.
    def name(self, example):
        return example[0].case_id

    async def run(self, example, bundle):
        """One scored run of `example` with `bundle`; the result carries a `record`."""
        return await run_one(
            *example,
            strategy=self.strategy,
            bundle=bundle,
            model=self.model,
            profile=self.profile,
        )

    def read(self, example, item):
        """(record, trajectory for reflection, frugality in [0, 1]) of one finished run."""
        record = {**item["record"], "claim_count": len(item["analysis"]["merged"]["claims"])}
        trajectory = {
            "record": record,
            "subtasks": item["analysis"]["subtasks"],
            "feedback": feedback(record),
        }
        return record, trajectory, 1 - record["model_calls"] / 14

    def note(self, record):
        codes = (c for v in record["failed_subtasks"].values() for c in v)
        return ", ".join([*record["critical_failures"], *codes])

    def evaluate(self, batch, candidate, capture_traces=False):
        from gepa import EvaluationBatch

        oversized = [k for k, text in candidate.items() if len(text) > MAX_COMPONENT_CHARS]
        bundle = None if oversized else self.bundle(candidate)
        gate = asyncio.Semaphore(self.parallel)

        async def one(example):
            if bundle is None:
                return None
            async with gate:
                for wait in (*self.retry_waits, None):
                    try:
                        item = await self.run(example, bundle)
                    except Exception as exc:  # one bad example must not abort the search
                        return exc
                    if not item["record"]["provider_error"]:
                        return item
                    if wait is None:
                        # Scoring an outage as 0 would poison the search; stop instead.
                        raise RuntimeError("model provider unavailable; rerun to resume")
                    await asyncio.sleep(wait)

        async def many():
            return await asyncio.gather(*(one(example) for example in batch))

        outputs, scores, trajectories, objectives = [], [], [], []
        for example, item in zip(batch, self.loop.run_until_complete(many()), strict=True):
            if item is None or isinstance(item, Exception):
                reason = (
                    f"Component over {MAX_COMPONENT_CHARS} characters: {oversized}"
                    if item is None
                    else f"Run error: {type(item).__name__}"
                )
                record = {"case_id": self.name(example), "score": 0.0, "error": reason}
                trajectory = {"record": record, "subtasks": [], "feedback": reason}
                frugality = 0.0
            else:
                record, trajectory, frugality = self.read(example, item)
            outputs.append(record)
            scores.append(record["score"])
            trajectories.append(trajectory)
            objectives.append({"quality": record["score"], "frugality": frugality})
        self.log.append(
            {
                "bundle": bundle.content_hash if bundle else None,
                "cases": [self.name(example) for example in batch],
                "scores": scores,
                "notes": [output.get("error") or self.note(output) for output in outputs],
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


REVIEW_TEMPLATE = """One read-only reviewer in a retail sourcing system reads the documents of a \
single supplier (a price list, notices, terms, a delivery record) and returns an offer card \
for one requested item. The text below is the only part of the reviewer's prompt you may \
change. The card format, the citation rule, the tool and the safety rules are fixed elsewhere \
and must not be restated or changed.
```
<curr_param>
```

These are readings of different suppliers: what the reviewer returned, and feedback from an \
automatic check against what the documents really support.
```
<side_info>
```

Write an improved text for this reviewer. Keep its purpose. Add only what the feedback shows \
is needed, as general reading rules in plain sentences. Do not define an output schema, do not \
mention specific suppliers, items, prices or dates, and stay under 1200 characters.

Provide the new text within ``` blocks."""


def explain_feedback(record):
    """Plain-language account of one explanation of a true proposal."""
    lines = [f"Score {record['score']:.2f} (0 means no usable answer or a contradiction)."]
    if record["failed_subtasks"]:
        lines.append("No usable answer: " + json.dumps(record["failed_subtasks"]) + ".")
    elif record["missing"]:
        lines.append(
            "Required typed claims that were not stated (format type:candidate_id=result): "
            + ", ".join(record["missing"])
            + "."
        )
    if record["contradictions"]:
        lines.append(
            "Typed claims that contradict the solver output: "
            + ", ".join(record["contradictions"])
            + ". Every typed claim must restate a solver field exactly."
        )
    if record["unverifiable"]:
        lines.append(f"{record['unverifiable']} typed claims used results outside the vocabulary.")
    return " ".join(lines)


def read_feedback(record, supplier):
    """Plain-language account of one supplier reading, with what the documents support."""
    lines = [
        f"Score {record['score']:.2f} (0 means no accepted card, or a field that decides the "
        "purchase was wrong)."
    ]
    for attempt, made in enumerate(record["attempts"], 1):
        if made["problems"]:
            why = "; ".join(made["reasons"]) or ", ".join(made["problems"])
            lines.append(f"Reading {attempt} was rejected by the citation check: {why}.")
    if record["attempts"][-1]["problems"]:
        # Without a card there is nothing to compare field by field.
        return " ".join([*lines, "No card was accepted for this supplier."])
    stated = {"deliveries": "history", "late": "history", "reason": "status"}
    for item in record["wrong"]:
        where = supplier["evidence"].get(stated.get(item["field"], item["field"]), [])
        lines.append(
            f"{item['field']}: returned {json.dumps(item['got'])}, the documents support "
            f"{json.dumps(item['expected'])}" + (f" (see {', '.join(where)})." if where else ".")
        )
    if record["passed"] and not record["first_reading"]:
        lines.append("The card was right only on the second reading.")
    return " ".join(lines)


class StageAdapter(CaseBundleAdapter):
    """GEPAAdapter over one stage of the sourcing loop. One metric call is one run of that stage.

    An example is (world, supplier or None, replicate); see `stages.items`.
    """

    def __init__(self, *, base, stage, model, profile, role_models=None, parallel=3):
        super().__init__(base=base, strategy=None, model=model, profile=profile, parallel=parallel)
        self.stage, self.role_models = stage, role_models

    def name(self, example):
        world, supplier, _ = example
        return world["case_id"] + (f":{supplier['supplier_id']}" if supplier else "")

    async def run(self, example, bundle):
        from .stages import run_item

        world, supplier, replicate = example
        record, outcome = await run_item(
            self.stage,
            world,
            supplier,
            bundle=bundle,
            model=self.model,
            profile=self.profile,
            role_models=self.role_models,
            replicate=replicate,
        )
        return {"record": record, "outcome": outcome}

    def read(self, example, item):
        record, outcome, supplier = item["record"], item["outcome"], example[1]
        if self.stage == "explain":
            trajectory = {
                "record": record,
                "subtasks": outcome["subtasks"],
                "feedback": explain_feedback(record),
            }
            return record, trajectory, 1.0
        trajectory = {
            "record": record,
            "supplier": supplier,
            "card": outcome["card"],
            "feedback": read_feedback(record, supplier),
        }
        # A card that needed its second reading cost twice as much.
        return record, trajectory, 1.0 if record["first_reading"] else 0.5

    def note(self, record):
        from .stages import failure_kinds

        return "" if record["passed"] else ", ".join(failure_kinds(record))

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        if self.stage == "explain":
            return super().make_reflective_dataset(candidate, eval_batch, components_to_update)
        rows = []
        for trajectory in eval_batch.trajectories:
            supplier, card = trajectory.get("supplier"), trajectory.get("card")
            kinds = sorted(doc["kind"] for doc in supplier["documents"]) if supplier else []
            rows.append(
                {
                    "Inputs": "One supplier's documents (" + ", ".join(kinds) + ") and a request.",
                    "Generated Outputs": {
                        key: card[key] for key in ("status", "reason", "offer", "history")
                    }
                    if card
                    else "no accepted card",
                    "Feedback": trajectory["feedback"],
                }
            )
        return {component: rows for component in components_to_update}


def _search(
    adapter,
    train,
    val,
    *,
    reflection_model,
    components,
    template,
    max_metric_calls,
    run_dir,
    **gepa_options,
):
    import gepa

    def reflect(prompt):
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        reply = adapter.loop.run_until_complete(reflection_model.complete(messages, []))
        adapter.reflections.append(reply["content"])
        return reply["content"]

    Path(run_dir).mkdir(parents=True, exist_ok=True)
    result = gepa.optimize(
        seed_candidate={name: adapter.base.components[name] for name in components},
        trainset=train,
        valset=val,
        adapter=adapter,
        reflection_lm=reflect,
        max_metric_calls=max_metric_calls,
        run_dir=str(run_dir),
        reflection_prompt_template=template,
        display_progress_bar=False,
        raise_on_exception=True,
        **gepa_options,
    )
    return result.best_candidate, result, adapter


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
    adapter = CaseBundleAdapter(
        base=base, strategy=strategy, model=task_model, profile=task_profile, parallel=parallel
    )
    if any(pair[1]["partition"] not in ("evo-train", "evo-val") for pair in pairs):
        raise ValueError("only evo-train and evo-val cases may be given to the optimizer")
    return _search(
        adapter,
        [pair for pair in pairs if pair[1]["partition"] == "evo-train"],
        [pair for pair in pairs if pair[1]["partition"] == "evo-val"],
        reflection_model=reflection_model,
        components=components,
        template=REFLECTION_TEMPLATE,
        max_metric_calls=max_metric_calls,
        run_dir=run_dir,
        seed=seed,
        reflection_minibatch_size=minibatch,
    )


def evolve_stage(
    worlds,
    *,
    base,
    stage,
    task_model,
    task_profile,
    reflection_model,
    components,
    max_metric_calls,
    run_dir,
    role_models=None,
    val_replicates=3,
    seed=0,
    minibatch=3,
    parallel=3,
):
    """Evolve the text of one sourcing stage. Returns (best components, GEPA result, adapter).

    A single run of a stage is noisy, so every validation item is run `val_replicates`
    times; training items are run once per minibatch, where the feedback matters.
    """
    from .stages import items

    if any(world["partition"] not in ("evo-train", "evo-val") for world in worlds):
        raise ValueError("only evo-train and evo-val worlds may be given to the optimizer")
    adapter = StageAdapter(
        base=base,
        stage=stage,
        model=task_model,
        profile=task_profile,
        role_models=role_models,
        parallel=parallel,
    )

    def examples(partition, replicates):
        chosen = [world for world in worlds if world["partition"] == partition]
        return [
            (world, supplier, replicate)
            for world, supplier in items(chosen, stage)
            for replicate in range(1, replicates + 1)
        ]

    return _search(
        adapter,
        examples("evo-train", 1),
        examples("evo-val", val_replicates),
        reflection_model=reflection_model,
        components=components,
        template=REFLECTION_TEMPLATE if stage == "explain" else REVIEW_TEMPLATE,
        max_metric_calls=max_metric_calls,
        run_dir=run_dir,
        seed=seed,
        reflection_minibatch_size=minibatch,
    )
