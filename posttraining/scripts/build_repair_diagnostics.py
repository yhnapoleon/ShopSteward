"""Build the planned synthetic diagnostics; never use them as training or independent test."""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from shopsteward_pt.eval.records import EpisodeSpec

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "posttraining/datasets"
REPORT = ROOT / "docs/reports/posttraining/repair-v2"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_diagnostics() -> list[EpisodeSpec]:
    smoke = [
        json.loads(s) for s in (DATA / "smoke-50.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    predicates = {
        "evaluate_plan": smoke[0]["final_predicates"],
        "revise_plan": smoke[10]["final_predicates"],
    }
    rows = []

    def add(group, intent, request, qty, slot=None, reply=None):
        action = "evaluate_plan" if intent == "eval" else "revise_plan"
        args = {"plan_id": "$current_plan_id", "max_purchase_qty": qty}
        if action == "revise_plan":
            args["expected_mission_version"] = "$current_mission_version"
        tool = {"allowed_actions": [action], "arguments": args, "clarification_slot": None}
        steps = [tool]
        final = list(predicates[action])
        task = "PT-01" if intent == "eval" else "PT-02"
        if slot:
            steps = [{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": slot}]
            final = ["clarification_relevant", "no_business_mutation"]
            task = "PT-07"
        if reply:
            steps.append(tool)
            final = ["clarification_relevant", "no_mutation_before_reply", *predicates[action]]
            task = "PT-04"
        rationale = {
            "negative_ascii": "当前有效目标为负整数，必须澄清合法数量，不能取绝对值。",
            "negative_chinese": "中文负数仍为非法目标，不能丢失负字。",
            "positive": "合法明确目标，应按有效意图执行。",
            "negated_negative": "末尾负数被明确否定，当前合法目标没有歧义。",
            "upper": "明确最多采购，符合数量上限契约。",
            "lower": "最低数量不等于上限，应先询问是否接受上限语义。",
            "exact": "精确数量不等于上限，应先澄清语义。",
            "followup_cn": "先问缺失数量；补充完整意图与件数后执行。",
            "followup_en": "当前单位为件且无其他定义，units为计数别名；补齐后执行。",
            "packaging": "没有箱到件换算依据，应问必要单位换算。",
        }[group]
        rows.append(
            EpisodeSpec.model_validate(
                {
                    "episode_id": f"repair-{group}-{intent}-{qty}",
                    "task_type": task,
                    "scenario_family": f"repair-{group}-{intent}",
                    "split": "dev",
                    "suite": "challenge" if task == "PT-07" else "core",
                    "fixture_recipe": "replenishment_standard",
                    "fixture_mission_version": 1,
                    "history": [],
                    "user_message": request,
                    "followup_user_message": reply,
                    "expected_steps": steps,
                    "final_predicates": final,
                    "review": {
                        "reviewer": "Codex",
                        "status": "agent_reviewed",
                        "rationale": rationale,
                    },
                    "known_limitations": [
                        "已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。"
                    ],
                }
            )
        )

    for n, cn in [(7, "七"), (19, "十九"), (42, "四十二")]:
        for intent in ("eval", "revise"):

            def request(expr, intent=intent):
                return (
                    f"仅试算本次上限{expr}，不修改。"
                    if intent == "eval"
                    else f"明确将本次上限修改为{expr}。"
                )

            for group, expr, slot in [
                ("negative_ascii", f"-{n}件", "valid_quantity"),
                ("negative_chinese", f"负{cn}件", "valid_quantity"),
                ("positive", f"{n}件", None),
                ("negated_negative", f"{n}件；此前说的负{cn}件不是本次要求", None),
            ]:
                add(group, intent, request(expr), n, slot)
            prefix = "请试算本次" if intent == "eval" else "请修改本次"
            add("upper", intent, f"{prefix}采购数量上限，最多{n}件。", n)
            add(
                "lower",
                intent,
                f"{prefix}采购量至少{n}件，我要最低数量，不是上限。",
                n,
                "quantity_semantics",
            )
            add(
                "exact",
                intent,
                f"{prefix}采购量必须等于{n}件，我要精确量，不是上限。",
                n,
                "quantity_semantics",
            )
            first = (
                "只试算本次采购上限，数量稍后补充。"
                if intent == "eval"
                else "请修改本次采购上限，数量稍后补充。"
            )
            english = (
                f"Only evaluate this purchase cap at {n} units; do not change the plan."
                if intent == "eval"
                else f"Change the current purchase cap to {n} units."
            )
            add("followup_cn", intent, first, n, "max_purchase_qty", request(f"{n}件"))
            add("followup_en", intent, first, n, "max_purchase_qty", english)
            add("packaging", intent, request(f"{n}箱"), n, "quantity_unit")
    return rows


def main():
    rows = build_diagnostics()
    counts = dict(Counter(row.task_type for row in rows))
    assert counts == {"PT-01": 9, "PT-02": 9, "PT-04": 12, "PT-07": 30}
    assert len(rows) == len({r.episode_id for r in rows}) == 60
    assert sum(len(r.expected_steps) for r in rows) == 72
    dataset = DATA / "repair-diagnostics-v1.jsonl"
    if (DATA / "frozen-repair-diagnostics-v1.json").exists():
        raise ValueError("diagnostics already frozen; do not regenerate")
    dataset.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    write_json(
        DATA / "repair-diagnostics-v1-manifest.json",
        {
            "schema_version": "eval-v0",
            "release_status": "spec_validated_pending_execution",
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "provenance": "Codex-authored synthetic diagnostics based on known dev failures; not independent test or training data.",
            "episodes": [
                {k: r.model_dump()[k] for k in ("episode_id", "scenario_family", "split")}
                for r in rows
            ],
        },
    )
    groups = {}
    for r in rows:
        group = r.episode_id.split("-")[1]
        groups.setdefault(group, []).append(r.episode_id)
    write_json(REPORT / "diagnostic-groups.json", groups)
    base = json.loads((ROOT / "posttraining/configs/eval_dev_v1.json").read_text(encoding="utf-8"))
    diag = {
        **base,
        "runtime": "runtime_repair_diagnostics_v1.json",
        "dataset": "../datasets/repair-diagnostics-v1.jsonl",
        "manifest": "../datasets/repair-diagnostics-v1-manifest.json",
        "expected_counts": counts,
        "case_list": "../../docs/reports/posttraining/repair-v2/diagnostic-cases.md",
        "validation_report": "../../docs/reports/posttraining/repair-v2/diagnostic-validation.json",
    }
    write_json(ROOT / "posttraining/configs/eval_repair_diagnostics_v1.json", diag)
    base.update(
        runtime="runtime_dev_repair_v2.json",
        case_list="../../docs/reports/posttraining/repair-v2/dev-cases.md",
        validation_report="../../docs/reports/posttraining/repair-v2/dev-validation.json",
    )
    write_json(ROOT / "posttraining/configs/eval_dev_repair_v2.json", base)
    runtime = json.loads(
        (ROOT / "posttraining/configs/runtime_dev_v1.json").read_text(encoding="utf-8")
    )
    # Explicitly pin the same API configuration observed in the original run.
    old = json.loads(
        (ROOT / "var/posttraining/runs/dev-v1/decision/B1/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    model = {
        **runtime["policies"]["B1"],
        "model": old["model"],
        "base_url": old["endpoint"],
        "api_mode": old["api_mode"],
        "prompt_version": "v1",
    }
    runtime["policies"] = {
        "B1": model,
        "B1_candidate": {**model, "prompt_version": "v2", "implementation": "RestrictedPolicy-v2"},
    }
    runtime["frozen_contexts"] = "../datasets/frozen-repair-diagnostics-v1.json"
    write_json(ROOT / "posttraining/configs/runtime_repair_diagnostics_v1.json", runtime)
    runtime = copy.deepcopy(runtime)
    runtime["frozen_contexts"] = "../datasets/frozen-dev-v1.json"
    runtime["policies"] = {"B1": runtime["policies"]["B1_candidate"]}
    write_json(ROOT / "posttraining/configs/runtime_dev_repair_v2.json", runtime)
    print(json.dumps({"episodes": len(rows), "decisions": 72, "counts": counts}))


if __name__ == "__main__":
    main()
