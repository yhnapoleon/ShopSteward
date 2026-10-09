import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from test_case_scoring import bind_trace, payloads


def bundle(root):
    from shopsteward_pt.case_eval.models import RubricDefinition

    case, trace = payloads()
    fixture = b'{"notice":"illustrative fixture only"}\n'
    (root / "fixture.json").write_bytes(fixture)
    fixture_hash = hashlib.sha256(fixture).hexdigest()
    case["fixture_hash"] = trace["fixture_hash"] = fixture_hash
    trace = bind_trace(case, trace)
    files = {
        "rubric.json": RubricDefinition().model_dump_json(indent=2),
        "cases.jsonl": json.dumps(case) + "\n",
        "traces.jsonl": json.dumps(trace) + "\n",
        "reviews.jsonl": "",
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")

    def artifact(path):
        return {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}

    manifest = {
        "schema_version": "case_manifest_v1",
        "dataset_version": "example-dev-v1",
        "artifact_kind": "example",
        "rubric": artifact("rubric.json"),
        "cases": artifact("cases.jsonl"),
        "traces": artifact("traces.jsonl"),
        "reviews": artifact("reviews.jsonl"),
        "fixtures": [{"fixture_id": "golden", **artifact("fixture.json")}],
        "research_status": "development_only_pending_human_calibration",
        "locked_test_count": 0,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root / "manifest.json"


def test_offline_cli_scores_reports_and_rejects_modified_frozen_asset(tmp_path):
    from shopsteward_pt.case_eval.cli import main

    manifest = bundle(tmp_path)
    out = tmp_path / "out"
    assert main(["validate", "--manifest", str(manifest)]) == 0
    assert main(["score", "--manifest", str(manifest), "--output-dir", str(out)]) == 0
    results = [
        json.loads(line)
        for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert results[0]["task_success"] is True
    assert results[0]["artifact_kind"] == "example"
    report_out = tmp_path / "report"
    assert (
        main(["report", "--results", str(out / "results.jsonl"), "--output-dir", str(report_out)])
        == 0
    )
    assert (
        json.loads((report_out / "report.json").read_text(encoding="utf-8"))["groups"][0][
            "outcomes"
        ]["attempted"]
        == 1
    )
    (tmp_path / "cases.jsonl").write_text("{}\n", encoding="utf-8")
    assert main(["score", "--manifest", str(manifest), "--output-dir", str(tmp_path / "bad")]) == 1
    assert not (tmp_path / "bad").exists()


def test_module_cli_is_invocable_and_contract_schema_is_exported(tmp_path):
    manifest = bundle(tmp_path)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    completed = subprocess.run(
        [sys.executable, "-m", "shopsteward_pt.case_eval", "validate", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["cases"] == 1
    from shopsteward_pt.case_eval.cli import main

    assert main(["schemas", "--output-dir", str(tmp_path / "schemas")]) == 0
    schema = json.loads(
        (tmp_path / "schemas" / "CaseContract.schema.json").read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False


def test_manifest_cannot_read_outside_bundle(tmp_path):
    from shopsteward_pt.case_eval.cli import main

    manifest = bundle(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["cases"]["path"] = "../outside.jsonl"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert main(["validate", "--manifest", str(manifest)]) == 1
