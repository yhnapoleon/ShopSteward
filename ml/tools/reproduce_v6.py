"""Verify a checked-out bundle and reproduce a saved v6 prediction without a service."""

import argparse
import json
from pathlib import Path

import numpy as np

from shopsteward_ml.runtime import ForecastRuntime
from shopsteward_ml.schemas import PredictRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "var/forecast-v6/bundle",
    )
    parser.add_argument("--series-id", default="FOODS_1_014_CA_1")
    args = parser.parse_args()
    runtime = ForecastRuntime(args.bundle)
    demo = runtime.demo_history(args.series_id)
    result = runtime.predict(
        PredictRequest(
            store_id="group-example-store",
            sku_id="group-example-sku",
            series_id=args.series_id,
            history=demo["history"],
            observation_end_date=demo["observation_end_date"],
            timezone="UTC",
            input_state_version=1,
        )
    )
    reference = json.loads((args.bundle / "parity-reference.json").read_text(encoding="utf-8"))
    expected = sorted(
        (row for row in reference["champion"] if row["series_id"] == args.series_id),
        key=lambda row: row["horizon_step"],
    )
    actual = [row["quantity"] for row in result["daily_predictions"]]
    np.testing.assert_allclose(actual, [row["predicted"] for row in expected], rtol=1e-6, atol=1e-6)
    print(
        json.dumps(
            {
                "verification": "PASS",
                "label": "模型推演，仅供参考",
                "model_version": result["model_version"],
                "series_id": args.series_id,
                "daily_predictions": actual,
                "total_quantity_raw": result["total_quantity_raw"],
                "predicted_quantity": result["predicted_quantity"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
