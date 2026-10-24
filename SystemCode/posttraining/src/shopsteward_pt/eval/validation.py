"""Validate task specifications and export an inspectable case list, without execution."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from shopsteward_agent.task_policy.contracts import Contract

from shopsteward_pt.eval.records import EpisodeSpec


class ValidationConfig(Contract):
    dataset: str
    manifest: str
    task_contract: str
    expected_counts: dict[str, int]
    case_list: str
    validation_report: str
    schema_version: str = "eval-v0"
    runtime: str | None = None


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(base: Path, path: str) -> Path:
    return (base / path).resolve()


def _case_list(specs: list[EpisodeSpec], report: dict) -> str:
    lines = [
        "# smoke 案例清单",
        "",
        f"共 {report['episode_count']} 个 episode，{report['decision_target_count']} 个决策目标。",
        "",
        "本清单包含评测金标，不能作为模型输入。规格复核不等于真实工具执行或模型成绩。",
        f"Agent 复核：{report['agent_reviewed_count']}；人工复核：{report['human_reviewed_count']}；"
        f"执行验证：{report['execution_verified_count']}。",
        "",
        "| ID | 类型 | 请求 | 预期动作/参数或澄清缺项 | 后续回复 |",
        "|---|---|---|---|---|",
    ]

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", "<br>")

    for spec in specs:
        expected = " → ".join(
            step.allowed_actions[0]
            + " "
            + (
                "询问 " + step.clarification_slot
                if step.clarification_slot
                else json.dumps(step.arguments, ensure_ascii=False, sort_keys=True)
            )
            for step in spec.expected_steps
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in [
                    spec.episode_id,
                    spec.task_type,
                    spec.user_message,
                    expected,
                    spec.followup_user_message or "—",
                ]
            )
            + " |"
        )
    lines += ["", "## 逐例语义依据与重放前提", ""]
    for spec in specs:
        lines += [
            f"### {spec.episode_id}",
            "",
            f"来源家族：`{spec.scenario_family}`；fixture：`{spec.fixture_recipe}`；"
            f"当前版本 recipe：{spec.fixture_mission_version}。",
            f"复核：{spec.review.status} / {spec.review.reviewer}。{spec.review.rationale}",
        ]
        for turn in spec.history:
            lines.append(
                f"历史：{turn.user_message} → {turn.action}，上限 "
                f"{json.dumps(turn.max_purchase_qty)}；对象 {turn.plan_reference}。"
            )
        lines.append("成功谓词：" + "、".join(spec.final_predicates) + "。")
        lines.extend("待验证/限制：" + item for item in spec.known_limitations)
        lines.append("")
    return "\n".join(lines)


def validate_config(config_path: Path, *, output_dir: Path | None = None) -> dict:
    config_path = Path(config_path).resolve()
    config = ValidationConfig.model_validate(read_json(config_path))
    base = config_path.parent
    dataset = _resolve(base, config.dataset)
    specs = []
    for line_number, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            specs.append(EpisodeSpec.model_validate(json.loads(line)))
        except ValueError as exc:
            raise ValueError(f"{dataset.name}:{line_number}: {exc}") from exc
    if not specs:
        raise ValueError("empty episode dataset")
    ids = [spec.episode_id for spec in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate episode ID")
    contract = read_json(_resolve(base, config.task_contract))
    if contract["schema_version"] != config.schema_version:
        raise ValueError("task contract schema version mismatch")
    for spec in specs:
        if spec.fixture_recipe not in contract["fixture_recipes"]:
            raise ValueError(f"{spec.episode_id}: unknown fixture recipe")
        if spec.task_type not in contract["tasks"]:
            raise ValueError(f"{spec.episode_id}: unknown task")
    counts = dict(sorted(Counter(spec.task_type for spec in specs).items()))
    if counts != config.expected_counts:
        raise ValueError(
            f"task counts mismatch: actual={counts}, expected={config.expected_counts}"
        )
    manifest = read_json(_resolve(base, config.manifest))
    sha256 = hashlib.sha256(dataset.read_bytes()).hexdigest()
    if manifest["schema_version"] != config.schema_version:
        raise ValueError("manifest schema version mismatch")
    if manifest["dataset_sha256"] != sha256:
        raise ValueError("dataset hash differs from manifest")
    entries = manifest["episodes"]
    indexed = {entry["episode_id"]: entry for entry in entries}
    if len(indexed) != len(entries) or set(indexed) != set(ids):
        raise ValueError("manifest episode IDs do not match dataset")
    families = {}
    for spec in specs:
        entry = indexed[spec.episode_id]
        if (entry["scenario_family"], entry["split"]) != (spec.scenario_family, spec.split):
            raise ValueError(f"{spec.episode_id}: manifest split/family mismatch")
        previous = families.setdefault(spec.scenario_family, spec.split)
        if previous != spec.split:
            raise ValueError(f"family crosses splits: {spec.scenario_family}")
    report = {
        "status": "spec_validated",
        "schema_version": config.schema_version,
        "release_status": manifest["release_status"],
        "dataset_sha256": sha256,
        "episode_count": len(specs),
        "decision_target_count": sum(len(s.expected_steps) for s in specs),
        "task_counts": counts,
        "suite_counts": dict(Counter(s.suite for s in specs)),
        "split_counts": dict(Counter(s.split for s in specs)),
        "family_count": len(families),
        "family_counts": dict(sorted(Counter(s.scenario_family for s in specs).items())),
        "agent_reviewed_count": sum(s.review.status == "agent_reviewed" for s in specs),
        "human_reviewed_count": sum(s.review.status == "human_reviewed" for s in specs),
        "execution_verified_count": sum(s.execution_status == "verified" for s in specs),
        "model_evaluation": "not_run",
    }
    for configured, content in (
        (config.case_list, _case_list(specs, report)),
        (config.validation_report, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
    ):
        target = (
            Path(output_dir) / Path(configured).name if output_dir else _resolve(base, configured)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return report
