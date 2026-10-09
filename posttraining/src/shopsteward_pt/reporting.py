"""Numerators, denominators, latency and cost computed from saved evidence."""

import csv
import json
from collections import Counter
from pathlib import Path


def _ratio(correct, total):
    return {"correct": correct, "total": total, "rate": correct / total if total else None}


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def summarize(scores, traces):
    steps = [step for score in scores for step in score.per_step]
    attempted = [s for s in steps if s.attempted]
    tools = [s for s in steps if s.expected_tool]
    initial = [s.per_step[0] for s in scores]
    needed = [s for s in initial if s.expected_action == "clarify"]
    sufficient = [s for s in initial if s.expected_action != "clarify"]
    core = [s for s in scores if s.suite == "core"]
    execution = bool(scores) and scores[0].mode == "execution"
    amounts = [t.cost.get("amount") for t in traces]
    currencies = {t.cost.get("currency") for t in traces}
    complete_cost = bool(amounts) and all(a is not None for a in amounts) and len(currencies) == 1
    total_cost = sum(amounts) if complete_cost else None
    successes = sum(
        (s.episode_success if execution else s.decision_success) is True for s in scores
    )
    latencies = [r.latency_ms for t in traces for r in t.steps]
    task_latencies = [t.timing["task_ms"] for t in traces if t.timing.get("task_ms") is not None]
    usage = [r.usage for t in traces for r in t.steps]
    confusion = Counter(
        f"{s.expected_action}->{s.predicted_action or 'invalid/missing'}" for s in steps
    )
    return {
        "scheduled_episodes": len(scores),
        "attempted_decisions": len(attempted),
        "responded_decisions": sum(r.raw_response != {} for t in traces for r in t.steps),
        "environment_errors": sum(t.environment_error is not None for t in traces),
        "pending_reviews": sum(s.review_status == "pending_review" for s in scores),
        "action_accuracy": _ratio(sum(s.action_correct is True for s in attempted), len(attempted)),
        "effective_action_completion": _ratio(
            sum(s.action_correct is True for s in steps), len(steps)
        ),
        "arguments_accuracy": _ratio(sum(s.arguments_correct is True for s in tools), len(tools)),
        "format_validity": _ratio(sum(s.format_valid is True for s in attempted), len(attempted)),
        "decision_success": _ratio(sum(s.decision_success is True for s in scores), len(scores)),
        "core_success": _ratio(sum(s.episode_success is True for s in core), len(core))
        if execution
        else None,
        "clarification_recall": _ratio(
            sum(s.clarification_correct is True for s in needed), len(needed)
        ),
        "unnecessary_clarification": _ratio(
            sum(s.predicted_action == "clarify" for s in sufficient), len(sufficient)
        ),
        "scope_routing": {
            action: _ratio(
                sum(s.action_correct is True for s in initial if s.expected_action == action),
                sum(s.expected_action == action for s in initial),
            )
            for action in ("handoff", "no_action")
        },
        "step_coverage": _ratio(len(attempted), len(steps)),
        "wrong_write_attempts": sum(s.wrong_write_attempts for s in scores),
        "unexpected_business_mutations": sum(s.unexpected_business_mutation for s in scores),
        "confusion_matrix": dict(sorted(confusion.items())),
        "argument_errors": dict(Counter(e for s in steps for e in s.argument_errors)),
        "failure_counts": dict(Counter(e for s in scores for e in s.failure_tags)),
        "latency_ms": {
            "decision_p50": _percentile(latencies, 0.5),
            "decision_p95": _percentile(latencies, 0.95),
            "task_p50": _percentile(task_latencies, 0.5),
            "task_p95": _percentile(task_latencies, 0.95),
        },
        "tokens": {
            "input": sum(u.get("input_tokens", 0) for u in usage if u),
            "output": sum(u.get("output_tokens", 0) for u in usage if u),
            "missing_usage": sum(u is None for u in usage),
        },
        "cost": {
            "amount": total_cost,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "missing_count": sum(a is None for a in amounts),
            "per_success": total_cost / successes if total_cost is not None and successes else None,
            "success_basis": "episode" if execution else "decision_only",
        },
    }


def write_report(run_dir, scores, traces, specs):
    run_dir = Path(run_dir)
    summary = summarize(scores, traces)
    summary["by_task"] = {
        task: summarize(
            [s for s in scores if s.task_type == task],
            [t for s, t in zip(scores, traces, strict=True) if s.task_type == task],
        )
        for task in sorted({s.task_type for s in scores})
    }
    summary["by_suite"] = {
        suite: summarize(
            [s for s in scores if s.suite == suite],
            [t for s, t in zip(scores, traces, strict=True) if s.suite == suite],
        )
        for suite in sorted({s.suite for s in scores})
    }
    summary["by_family"] = {
        family: summarize(
            [s for s in scores if s.scenario_family == family],
            [t for s, t in zip(scores, traces, strict=True) if s.scenario_family == family],
        )
        for family in sorted({s.scenario_family for s in scores})
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (run_dir / "failures.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "episode_id",
                "task_type",
                "request",
                "expected",
                "predicted",
                "failure_tags",
                "review_status",
            ]
        )
        for score, trace in zip(scores, traces, strict=True):
            if score.failure_tags or score.review_status == "pending_review":
                spec = specs[score.episode_id]
                writer.writerow(
                    [
                        score.episode_id,
                        score.task_type,
                        spec.user_message,
                        json.dumps(
                            [s.model_dump() for s in spec.expected_steps], ensure_ascii=False
                        ),
                        json.dumps(
                            [
                                r.decision.model_dump() if r.decision else r.parse_error
                                for r in trace.steps
                            ],
                            ensure_ascii=False,
                        ),
                        ";".join(score.failure_tags),
                        score.review_status,
                    ]
                )

    def fmt(value):
        return (
            "未测"
            if value is None
            else f"{value['correct']}/{value['total']} ({value['rate']:.1%})"
            if value["rate"] is not None
            else "无样本"
        )

    lines = [
        "# Eval结果",
        "",
        f"模型/策略：{traces[0].policy_id if traces else '无'}；模式：{traces[0].mode if traces else '无'}。",
        f"episode：{len(scores)}；环境失败：{summary['environment_errors']}；待复核：{summary['pending_reviews']}。",
        "",
        "| 任务 | 动作正确 | 完整参数正确 | 核心任务成功 |",
        "|---|---|---|---|",
    ]
    for task, part in summary["by_task"].items():
        lines.append(
            f"| {task} | {fmt(part['action_accuracy'])} | {fmt(part['arguments_accuracy'])} | {fmt(part['core_success'])} |"
        )
    lines += [
        "",
        "成本与时间（缺失价格不填0；脚本澄清不含用户等待）：",
        "```json",
        json.dumps(
            {
                k: summary[k]
                for k in ("latency_ms", "tokens", "cost", "failure_counts", "confusion_matrix")
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "逐例证据见raw.jsonl、scores.jsonl、failures.csv；模型决策得分不代表真实业务执行成功。",
    ]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
