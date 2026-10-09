"""Offline paired repair results and explicit followup denominators."""

import argparse
import json
from pathlib import Path


def rows(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def ratio(correct, total):
    return {"correct": correct, "total": total, "rate": correct / total if total else None}


def summarize_followups(specs, traces, scores) -> dict:
    ids = {s["episode_id"] for s in specs if s["followup_user_message"] is not None}
    indexed = {s["episode_id"]: s for s in scores}
    traced = {t["episode_id"]: t for t in traces}
    complete = repeated = missing = calls = successes = 0
    for key in ids:
        trace, score = traced.get(key, {}), indexed.get(key, {})
        steps = trace.get("steps", [])
        calls += len(steps)
        successes += score.get("decision_success") is True
        missing += len(steps) < 2
        repeated += len(steps) > 1 and (steps[1].get("decision") or {}).get("name") == "clarify"
        scored = score.get("per_step", [])
        complete += (
            len(scored) > 1
            and scored[1].get("action_correct") is True
            and scored[1].get("arguments_correct") is True
        )
    return {
        "completion": ratio(complete, len(ids)),
        "repeated_clarification": ratio(repeated, len(ids)),
        "missing_followup": missing,
        "model_calls": calls,
        "model_calls_per_success": calls / successes if successes else None,
    }


def compare_scores(before, after, mode):
    field = "episode_success" if mode == "execution" else "decision_success"
    old, new = ({r["episode_id"]: r[field] for r in records} for records in (before, after))
    if set(old) != set(new):
        raise ValueError("paired comparison requires identical episode IDs")
    return {
        "fixed": sorted(k for k in old if old[k] is False and new[k] is True),
        "regressed": sorted(k for k in old if old[k] is True and new[k] is False),
        "persistent_failures": sorted(k for k in old if old[k] is False and new[k] is False),
        "pending": sorted(k for k in old if old[k] is None or new[k] is None),
    }


def compare_runs(old_dir, new_dir) -> dict:
    old, new = load_run(old_dir), load_run(new_dir)
    if old["mode"] != new["mode"]:
        raise ValueError("cannot pair different modes")
    return compare_scores(old["scores"], new["scores"], old["mode"])


def load_run(directory):
    specs, traces, scores = (
        rows(directory / name) for name in ("specs.jsonl", "raw.jsonl", "scores.jsonl")
    )
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    mode = traces[0]["mode"]
    successes = sum(
        s["episode_success" if mode == "execution" else "decision_success"] is True for s in scores
    )
    calls = sum(len(t["steps"]) for t in traces)
    usages = [s.get("usage") for t in traces for s in t["steps"]]
    known = all(u is not None for u in usages)
    inputs = sum(u.get("input_tokens", 0) for u in usages if u is not None)
    outputs = sum(u.get("output_tokens", 0) for u in usages if u is not None)
    return {
        "mode": mode,
        "summary": summary,
        "scores": scores,
        "followups": summarize_followups(specs, traces, scores),
        "usage": {
            "formal_calls": calls,
            "successful_tasks": successes,
            "calls_per_success": calls / successes if successes else None,
            "observed_input_tokens": inputs,
            "observed_output_tokens": outputs,
            "complete_usage": known,
            "tokens_per_success": (inputs + outputs) / successes if successes and known else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline", "candidate", "diagnostics", "output"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    groups = json.loads((args.output / "diagnostic-groups.json").read_text(encoding="utf-8"))
    result = {
        "diagnostics": {},
        "full": {},
        "caveat": "Historical dev comparison differs in call time and execution fixtures; diagnostics compare prompt versions on shared frozen inputs. Agent-reviewed synthetic dev only.",
    }
    lines = [
        "# 受限决策修复复评",
        "",
        result["caveat"],
        "",
        "## 针对性诊断",
        "",
        "| 分类 | v1 | v2 |",
        "|---|---:|---:|",
    ]
    for policy in ("B1", "B1_candidate"):
        run = load_run(args.diagnostics / "decision" / policy)
        indexed = {s["episode_id"]: s for s in run["scores"]}
        run["groups"] = {
            key: ratio(sum(indexed[i]["decision_success"] is True for i in ids), len(ids))
            for key, ids in groups.items()
        }
        result["diagnostics"][policy] = run
    diag = result["diagnostics"]
    for group in groups:
        values = [diag[p]["groups"][group] for p in ("B1", "B1_candidate")]
        lines.append(
            f"| {group} | {values[0]['correct']}/{values[0]['total']} | {values[1]['correct']}/{values[1]['total']} |"
        )
    result["diagnostic_changes"] = compare_scores(
        diag["B1"]["scores"], diag["B1_candidate"]["scores"], "decision"
    )
    lines += [
        "",
        "## 原dev复评",
        "",
        "| 模式 | v1任务成功 | v2任务成功 | 修复 | 新失败 |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in ("decision", "execution"):
        target = args.candidate / mode / "B1"
        if not (target / "summary.json").exists():
            continue
        old, new = load_run(args.baseline / mode / "B1"), load_run(target)
        changes = compare_scores(old["scores"], new["scores"], mode)
        result["full"][mode] = {"baseline": old, "candidate": new, "changes": changes}
        a, b = old["usage"], new["usage"]
        lines.append(
            f"| {mode} | {a['successful_tasks']}/{len(old['scores'])} | {b['successful_tasks']}/{len(new['scores'])} | {len(changes['fixed'])} | {len(changes['regressed'])} |"
        )
        lines += ["", f"{mode}变化：`{json.dumps(changes, ensure_ascii=False)}`", ""]
    if not result["full"]:
        lines += ["", "全量尚未执行或候选未晋级；不能据此宣称全量收益。"]
    lines += [
        "",
        "每成功任务调用/token、第二步完成与重复澄清、原始指标及所有分母见comparison.json。金额未配置时为null；参数正确率仍只覆盖期望工具步骤。",
        "",
        "诊断变体来自已知失败，不用于训练或独立test。",
    ]
    (args.output / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"diagnostic_versions": len(diag), "full_modes": list(result["full"])}))


if __name__ == "__main__":
    main()
