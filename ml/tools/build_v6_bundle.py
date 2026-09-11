"""Build portable artifacts and bounded historical demo data without training."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

WEIGHTS = {"F6": 0.5, "F3": 0.25, "W2": 0.125, "N3": 0.125}


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def build(research, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_EMPTY: refuse to overwrite a shipped bundle")
    output.mkdir(parents=True, exist_ok=True)
    old = research / "var/forecast/experiments/demo-v5"
    new = research / "var/forecast/experiments/demo-v6"
    metadata = json.loads((new / "panels.json").read_text())["main"]
    write(output / "series.json", metadata)
    for arm in WEIGHTS:
        source = (
            new / "final_models/1885" / arm if arm.startswith("F") else old / "final_models" / arm
        )
        target = output / "components" / arm
        target.mkdir(parents=True)
        info = json.loads((source / "info.json").read_text())
        files = (
            list(info["model_files"].values())
            if arm.startswith("F")
            else ["model.pt" if arm == "N3" else "model.txt"]
        )
        for name in ["mapping.json", "info.json", *files]:
            shutil.copyfile(source / name, target / name)
    frame = pd.read_parquet(
        old / "prepared.parquet", filters=[("day_index", ">=", 1512), ("day_index", "<=", 1885)]
    )
    demo = output / "demo-history"
    demo.mkdir()
    for row in metadata:
        sid = row["series_id"]
        history = frame.loc[frame.series_id.eq(sid)].sort_values("day_index")
        assert len(history) == 374 and history.day_index.max() == 1885
        entries = [
            {
                "date": pd.Timestamp(r.date).date().isoformat(),
                "sold_quantity": int(r.sold_quantity),
                "complete": True,
            }
            for r in history.itertuples()
        ]
        write(
            demo / f"{sid}.json",
            {
                "series_id": sid,
                "observation_end_date": entries[-1]["date"],
                "history": entries,
                "source_kind": "historical_demo",
            },
        )
    review = json.loads((new / "review_metrics.json").read_text())
    confirmation = json.loads((new / "confirmation_metrics.json").read_text())
    # Expected first review origin is a test oracle only, not used by inference.
    references = {}
    for arm in [*WEIGHTS, "champion"]:
        source = old if arm in ("W2", "N3") else new
        expected = pd.read_parquet(source / "review" / f"{arm}.parquet")
        # Never package post-cutoff actual sales, including in test references.
        references[arm] = expected.loc[
            expected.origin.eq(1885), ["series_id", "origin", "horizon_step", "predicted"]
        ].to_dict("records")
    write(output / "parity-reference.json", references)
    hashes = {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    manifest = {
        "schema_version": "shopsteward-v6-bundle-v1",
        "model_version": "shopsteward-v6-1885",
        "feature_profile": "sales-calendar-v6-multiscale",
        "weights": WEIGHTS,
        "training_cutoff_day": 1885,
        "training_cutoff_date": "2016-03-27",
        "minimum_history_days": 84,
        "recommended_history_days": 374,
        "evaluation": {
            "historical_review_weeks": 8,
            "historical_weekly_wape": review["champion"]["weekly_wape"],
            "relative_gain_vs_v5": review["gain_vs_v5"],
            "confirmation_weeks": 4,
            "confirmation_weekly_wape": confirmation["champion"]["weekly_wape"],
            "confirmation_v5_weekly_wape": confirmation["V5"]["weekly_wape"],
            "independent_holdout": False,
            "production_validated": False,
        },
        "limitations": [
            "Historical M5 review reuses the v5 evaluation period; it is not an independent holdout.",
            "Eight-week WAPE 34.976%; improvement over v5 approximately 0.57%; additional four weeks slightly worse than v5.",
            "Sales-only forecast omits price, promotions, stockouts and events; demand is not procurement quantity.",
            "Only the 300 packaged identities are supported. Mapping an external SKU is an explicit user assumption.",
            "84 complete days are required; with fewer than 374 days, unavailable long-window features remain missing.",
        ],
        "sha256": hashes,
    }
    write(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "bundle": str(output.resolve()),
                "files": len(hashes) + 1,
                "bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
                "series": len(metadata),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("research_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.research_root, args.output)
