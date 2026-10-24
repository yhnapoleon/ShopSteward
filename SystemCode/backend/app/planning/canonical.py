from datetime import UTC, datetime

TIME_FIELDS = {
    "data_as_of",
    "simulation_time",
    "horizon_start",
    "horizon_end",
    "valid_from",
    "valid_until",
    "expected_arrival_at",
    "evaluated_at",
    "last_successful_sync_at",
    "source_fresh_until",
    "created_at",
    "expires_at",
}


def canonical(value, field=None):
    """Decision-v1 representation; source event receipts retain their original precision."""
    if isinstance(value, float):
        raise ValueError("Decision-v1 does not allow floating point values")
    if isinstance(value, dict):
        return {key: canonical(item, key) for key, item in value.items()}
    if isinstance(value, list):
        result = [canonical(item) for item in value]
        if field == "candidates":
            result.sort(key=lambda item: (item["quantity"], item["id"]))
        elif field == "inbound_items":
            result.sort(key=lambda item: (item["action_id"], item["sku_id"]))
        return result
    if value is not None and field in TIME_FIELDS:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            raise ValueError("Decision timestamps must include a timezone")
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return value
