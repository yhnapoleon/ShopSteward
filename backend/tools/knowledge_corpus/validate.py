"""Deterministic input validation, with safe per-line diagnostics."""

import json
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .schema import CASE, SCENARIO, SOURCE


def _validate(row, schema):
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(row),
        key=lambda e: str(list(e.path)),
    )
    if errors:
        e = errors[0]
        # Only schema field names, never user values, in diagnostics.
        detail = str(e.validator_value) if e.validator == "required" else e.validator
        raise ValueError(f"{'.'.join(map(str, e.path)) or 'record'}: invalid {detail}")
    return dict(row)


def validate_source(row: dict) -> dict:
    return _validate(row, SOURCE)


def validate_scenario(row: dict) -> dict:
    result = _validate(row, SCENARIO)
    interval = result["effective_interval"]
    if interval["from"] >= interval["until"]:
        raise ValueError("effective_interval must be nonempty and ordered")
    return result


def validate_case(row: dict) -> dict:
    return _validate(row, CASE)


def validate_case_splits(rows: list[dict]) -> None:
    families = defaultdict(set)
    ids = set()
    for row in rows:
        if row["case_id"] in ids or row["split"] not in {"dev", "test"}:
            raise ValueError("duplicate case_id or invalid split")
        ids.add(row["case_id"])
        families[("scenario", row["scenario_family_id"])].add(row["split"])
        for source in row.get("source_family_ids", []):
            families[("source", source)].add(row["split"])
    if any(len(splits) > 1 for splits in families.values()):
        raise ValueError("source/scenario family crosses dev/test")


def read_jsonl(path: Path, validator=None) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("expected object")
            rows.append(validator(row) if validator else row)
        except (ValueError, TypeError, KeyError) as error:
            message = "invalid JSON" if isinstance(error, json.JSONDecodeError) else str(error)
            raise ValueError(f"{Path(path).name}:{n}: {message}") from None
    return rows
