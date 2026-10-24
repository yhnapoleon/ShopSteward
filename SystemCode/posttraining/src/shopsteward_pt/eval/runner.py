"""Offline decisions and real-tool episodes with resumable clarification review."""

import json
from pathlib import Path
from time import perf_counter

from shopsteward_agent.task_policy.contracts import PolicyContext

from shopsteward_pt.eval.policies import make_policy
from shopsteward_pt.eval.records import EpisodeTrace
from shopsteward_pt.eval.scorers import clarification_review


def load_runtime(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    path = (config_path.parent / config["runtime"]).resolve()
    runtime = json.loads(path.read_text(encoding="utf-8"))
    for key in ("app_env_file", "run_root", "frozen_contexts"):
        runtime[key] = str((path.parent / runtime[key]).resolve())
    runtime["dataset"] = str((config_path.parent / config["dataset"]).resolve())
    return runtime


async def run_episode(
    spec, policy_id, *, mode, config, frozen_context=None, policy=None, reviews=None, previous=None
):
    policy = policy or make_policy(policy_id, config)
    reviews = reviews or {}
    trace = EpisodeTrace(episode_id=spec.episode_id, policy_id=policy_id, mode=mode)
    tool_ms = 0.0

    async def steps(context, fixture=None):
        nonlocal tool_ms
        trace.context = context.model_copy(deep=True)
        for index in range(len(spec.expected_steps)):
            trace.step_contexts.append(context.model_copy(deep=True))
            record = (
                previous.steps[index]
                if previous and index < len(previous.steps)
                else await policy.decide(context)
            )
            trace.steps.append(record)
            if record.decision is None:
                trace.delivery = {"kind": "protocol_error"}
                break
            decision = record.decision
            start = perf_counter()
            if fixture:
                outcome = await fixture.invoke(context.messages[-1]["content"], decision)
                if outcome.get("receipt"):
                    trace.receipts.append(outcome["receipt"])
                trace.delivery = outcome["delivery"]
            else:
                trace.delivery = {"kind": decision.name}
            tool_ms += (perf_counter() - start) * 1000
            if decision.name != "clarify":
                break
            if fixture:
                trace.state_after_clarify = await fixture.snapshot()
            if not spec.followup_user_message:
                break
            question = decision.arguments["question"]
            if clarification_review(spec, index, question, reviews) is not True:
                break
            context = context.model_copy(deep=True)
            context.messages += [
                {"role": "assistant", "content": question},
                {"role": "user", "content": spec.followup_user_message},
            ]

    try:
        if mode == "decision":
            if not frozen_context:
                raise ValueError("decision mode requires frozen real-fixture context")
            await steps(PolicyContext.model_validate(frozen_context))
        else:
            from shopsteward_pt.eval.fixtures import fixture_for

            async with fixture_for(spec, config) as fixture:
                trace.before_state = await fixture.snapshot()
                await steps(await fixture.context(spec.user_message), fixture)
                trace.after_state = await fixture.snapshot()
    except Exception as exc:
        # Error type is sufficient here; private connection details are not logged.
        trace.environment_error = (
            type(exc).__name__
            + ": "
            + (str(exc) if isinstance(exc, ValueError) else "runtime dependency failed")
        )
    trace.timing = {"task_ms": sum(s.latency_ms for s in trace.steps) + tool_ms, "tool_ms": tool_ms}
    price = config.get("policies", {}).get(policy_id, {}).get("price")
    usages = [r.usage for r in trace.steps]
    amount = 0.0 if policy_id == "B0" else None
    if price and usages and all(u is not None for u in usages):
        amount = (
            sum(
                u.get("input_tokens", 0) * price["input_per_million"]
                + u.get("output_tokens", 0) * price["output_per_million"]
                for u in usages
            )
            / 1e6
        )
    trace.cost = {
        "amount": amount,
        "currency": price["currency"] if price else "USD" if policy_id == "B0" else None,
    }
    return trace
