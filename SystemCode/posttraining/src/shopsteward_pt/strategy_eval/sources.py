"""Small public-data slices that ground the sourcing worlds.

Raw files stay outside Git. This writes only what the world generator reads:
real M5 demand weeks with their shelf prices, and DataCo's promised versus
actual shipping days. The output records each origin and raw-file hash, so a
world can be traced to public rows without redistributing either dataset.
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

# The forecast module's eight frozen test weeks (M5 day numbers of each Monday).
WEEK_STARTS = range(1886, 1942, 7)
DAILY_MEAN = (4, 40)  # busy enough to run short within a week, small enough to enumerate
NEIGHBORS = 40


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(item_id):
    return int(item_id.rsplit("_", 1)[1])


def m5_windows(raw, series_manifest):
    """Weeks of the project's frozen M5 series in which every day sold something."""
    raw = Path(raw)
    wanted = {
        (s["item_id"], s["store_id"]): s
        for s in json.loads(Path(series_manifest).read_text(encoding="utf-8"))["series"]
    }
    with open(raw / "calendar.csv", encoding="utf-8", newline="") as file:
        calendar = {day: row for day, row in enumerate(csv.DictReader(file), 1)}
    windows = []
    with open(raw / "sales_train_evaluation.csv", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        column = {name: index for index, name in enumerate(next(reader))}
        for row in reader:
            series = wanted.get((row[column["item_id"]], row[column["store_id"]]))
            if series is None:
                continue
            kept = []
            for start in WEEK_STARTS:
                demand = [int(row[column[f"d_{day}"]]) for day in range(start, start + 7)]
                if min(demand) > 0 and DAILY_MEAN[0] <= sum(demand) / 7 <= DAILY_MEAN[1]:
                    kept.append((start, demand))
            for start, demand in kept[:1] + kept[1:][-1:]:
                windows.append(
                    {
                        "series_id": series["series_id"],
                        "item_id": series["item_id"],
                        "dept_id": series["dept_id"],
                        "store_id": series["store_id"],
                        "week_start": calendar[start]["date"],
                        "wm_yr_wk": calendar[start]["wm_yr_wk"],
                        "demand": demand,
                    }
                )
    weeks = {(w["store_id"], w["wm_yr_wk"]) for w in windows}
    prices = {key: {} for key in weeks}
    with open(raw / "sell_prices.csv", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader)
        for store, item, week, price in reader:
            if (store, week) in prices:
                prices[(store, week)][item] = round(float(price) * 100)
    for window in windows:
        shelf = prices[(window["store_id"], window.pop("wm_yr_wk"))]
        window["sell_price_cents"] = shelf[window["item_id"]]
        prefix, number = window["dept_id"] + "_", _number(window["item_id"])
        near = sorted(
            (item for item in shelf if item.startswith(prefix) and item != window["item_id"]),
            key=lambda item: (abs(_number(item) - number), item),
        )[:NEIGHBORS]
        window["neighbors"] = [
            {"item_id": item, "sell_price_cents": shelf[item]} for item in sorted(near)
        ]
    return sorted(windows, key=lambda w: (w["series_id"], w["week_start"]))


def dataco_shipping(path):
    """Per shipping mode: the promised days and how many days delivery really took."""
    promised, actual, seen = {}, {}, set()
    with open(path, encoding="latin-1", newline="") as file:
        for row in csv.DictReader(file):
            # One shipment per order; cancelled orders were never delivered.
            if row["Order Id"] in seen or row["Delivery Status"] == "Shipping canceled":
                continue
            seen.add(row["Order Id"])
            mode = row["Shipping Mode"]
            promised.setdefault(mode, Counter())[int(row["Days for shipment (scheduled)"])] += 1
            actual.setdefault(mode, Counter())[int(row["Days for shipping (real)"])] += 1
    if any(len(days) != 1 for days in promised.values()):
        raise ValueError("a shipping mode has more than one promised lead time")
    return {
        mode: {
            "promised_days": next(iter(promised[mode])),
            "actual_days": {str(day): count for day, count in sorted(actual[mode].items())},
        }
        for mode in sorted(promised)
    }


def build(*, m5_raw, m5_series, dataco, out):
    m5_raw, dataco = Path(m5_raw), Path(dataco)
    sources = {
        "schema_version": "sourcing-sources-v1",
        "m5": {
            "source": "https://github.com/Mcompetitions/M5-methods",
            "terms_source": "https://github.com/Mcompetitions/M5-methods/blob/master/M5-Competitors-Guide.pdf",
            "raw_sha256": {
                name: _sha(m5_raw / name)
                for name in ("calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv")
            },
            "selection": "frozen 500 forecast series; test weeks d_1886..d_1941; every day sold "
            f"at least one unit and the daily mean is within {list(DAILY_MEAN)}; first and last "
            f"such week per series; {NEIGHBORS} same-department items nearest by item number",
            "windows": m5_windows(m5_raw, m5_series),
        },
        "dataco": {
            "source": "https://data.mendeley.com/datasets/8gx2fvg2k6/5",
            "doi": "10.17632/8gx2fvg2k6.5",
            "license": "CC BY 4.0",
            "attribution": "Constante, Silva, Pereira (2019), DataCo Smart Supply Chain for Big Data Analysis",
            "raw_sha256": {dataco.name: _sha(dataco)},
            "selection": "first row of each order, cancelled shipments excluded",
            "caveat": "actual days are almost uniform within a mode, so the publisher's data "
            "may itself be simulated; used only to draw delivery-history rows",
            "modes": dataco_shipping(dataco),
        },
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(sources, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return sources
