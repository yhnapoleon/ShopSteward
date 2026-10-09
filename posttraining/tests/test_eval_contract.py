import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def sample():
    return {
        "episode_id": "dev-pt01-001",
        "task_type": "PT-01",
        "scenario_family": "direct",
        "split": "dev",
        "suite": "core",
        "fixture_recipe": "replenishment_standard",
        "user_message": "如果上限20件呢？",
        "followup_user_message": None,
        "expected_steps": [
            {
                "allowed_actions": ["evaluate_plan"],
                "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 20},
                "clarification_slot": None,
            }
        ],
        "final_predicates": [
            "receipt_ok",
            "current_plan_unchanged",
            "task_constraints_unchanged",
            "cash_stock_transit_unchanged",
            "no_purchase_created",
        ],
        "review": {
            "reviewer": "codex",
            "status": "agent_reviewed",
            "rationale": "假设只试算，上限20不要求实际购买20。",
        },
        "execution_status": "not_run",
    }


def test_symbolic_gold_is_validated_without_becoming_model_input():
    from shopsteward_pt.eval.records import EpisodeSpec

    spec = EpisodeSpec.model_validate(sample())
    assert spec.expected_steps[0].arguments["plan_id"] == "$current_plan_id"
    assert spec.execution_status == "not_run"
    broken = sample()
    broken["expected_steps"][0]["arguments"]["max_purchase_qty"] = True
    with pytest.raises(ValidationError):
        EpisodeSpec.model_validate(broken)


@pytest.mark.parametrize(
    "change",
    [
        "missing_reply",
        "second_without_question",
        "unknown_predicate",
        "bad_placeholder",
        "wrong_suite",
        "missing_cap",
    ],
)
def test_incomplete_or_ambiguous_episode_specs_are_rejected(change):
    from shopsteward_pt.eval.records import EpisodeSpec

    row = sample()
    if change == "missing_reply":
        row["expected_steps"].insert(
            0,
            {
                "allowed_actions": ["clarify"],
                "arguments": {},
                "clarification_slot": "max_purchase_qty",
            },
        )
    elif change == "second_without_question":
        row["followup_user_message"] = "把上限改成20件"
        row["expected_steps"].append(copy.deepcopy(row["expected_steps"][0]))
    elif change == "unknown_predicate":
        row["final_predicates"] = ["everything_looks_good"]
    elif change == "bad_placeholder":
        row["expected_steps"][0]["arguments"]["plan_id"] = "$future_plan_id"
    elif change == "wrong_suite":
        row["suite"] = "challenge"
    else:
        del row["expected_steps"][0]["arguments"]["max_purchase_qty"]
    with pytest.raises(ValidationError):
        EpisodeSpec.model_validate(row)


def test_clarification_target_is_a_slot_not_an_exact_question():
    from shopsteward_pt.eval.records import EpisodeSpec

    row = sample()
    row.update(
        task_type="PT-04", user_message="把上限调低些", followup_user_message="把上限改成20件"
    )
    row["expected_steps"] = [
        {"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"},
        {
            "allowed_actions": ["revise_plan"],
            "arguments": {
                "plan_id": "$current_plan_id",
                "max_purchase_qty": 20,
                "expected_mission_version": "$current_mission_version",
            },
            "clarification_slot": None,
        },
    ]
    row["final_predicates"] = [
        "clarification_relevant",
        "receipt_ok",
        "revision_cap_matches",
        "purchase_within_cap",
        "old_plan_document_preserved",
        "new_plan_pending",
        "no_purchase_created",
    ]
    assert len(EpisodeSpec.model_validate(row).expected_steps) == 2


def write_config(tmp_path, rows):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    manifest = {
        "schema_version": "eval-v0",
        "release_status": "spec_only",
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "episodes": [
            {
                "episode_id": row["episode_id"],
                "scenario_family": row["scenario_family"],
                "split": row["split"],
            }
            for row in rows
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    config = {
        "dataset": "cases.jsonl",
        "manifest": "manifest.json",
        "task_contract": str(ROOT / "posttraining/tasks/replenishment_v0.json"),
        "expected_counts": {"PT-01": len(rows)},
        "case_list": "cases.md",
        "validation_report": "validation.json",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_validation_exports_readable_cases_without_claiming_execution(tmp_path):
    from shopsteward_pt.eval.validation import validate_config

    report = validate_config(write_config(tmp_path, [sample()]))
    assert report["episode_count"] == 1
    assert report["execution_verified_count"] == 0
    assert report["human_reviewed_count"] == 0
    listing = (tmp_path / "cases.md").read_text(encoding="utf-8")
    assert "如果上限20件呢？" in listing
    assert "evaluate_plan" in listing
    assert "max_purchase_qty" in listing


def test_duplicate_episode_and_changed_dataset_are_not_published(tmp_path):
    from shopsteward_pt.eval.validation import validate_config

    with pytest.raises(ValueError, match="duplicate episode"):
        validate_config(write_config(tmp_path, [sample(), sample()]))
    path = write_config(tmp_path, [sample()])
    with (tmp_path / "cases.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="hash"):
        validate_config(path)


def test_cli_runs_from_another_directory_and_returns_nonzero_for_invalid_input(tmp_path):
    path = write_config(tmp_path, [sample()])
    command = [sys.executable, "-m", "shopsteward_pt.cli", "validate", "--config", str(path)]
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(ROOT / "agent/src"), str(ROOT / "posttraining/src")]),
        PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["episode_count"] == 1
    (tmp_path / "cases.jsonl").write_text("invalid json\n", encoding="utf-8")
    result = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode != 0
    assert "validation failed" in result.stderr


def test_smoke_dataset_has_fifty_reviewed_specs_and_thirty_six_core_episodes(tmp_path):
    from shopsteward_pt.eval.validation import validate_config

    config_path = ROOT / "posttraining/configs/eval_smoke_v1.json"
    report = validate_config(config_path, output_dir=tmp_path)
    assert report["episode_count"] == 50
    assert report["suite_counts"] == {"core": 36, "challenge": 14}
    assert report["decision_target_count"] == 58
    assert report["task_counts"] == {
        "PT-01": 10,
        "PT-02": 10,
        "PT-03": 8,
        "PT-04": 8,
        "PT-05": 3,
        "PT-06": 3,
        "PT-07": 4,
        "PT-08": 2,
        "PT-09": 1,
        "PT-10": 1,
    }
    assert report["agent_reviewed_count"] == 50
    assert report["execution_verified_count"] == 0
