from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.config import TokenGrant
from app.core.errors import AppError
from app.reporting.read_pagination import decode_read_cursor, encode_read_cursor, read_scope
from app.reporting.read_router import SummaryQuery


def test_corrupt_record_log_preserves_identifier_without_payload():
    import json
    import logging

    from app.core.logging import JsonFormatter

    record = logging.LogRecord(
        "shopsteward", logging.WARNING, __file__, 1, "invalid_stored_read", (), None
    )
    record.record_id = "sale-123"
    record.record_type = "EventRow"
    record.document = {"secret": "must-not-appear"}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["record_id"] == "sale-123"
    assert payload["record_type"] == "EventRow"
    assert "secret" not in str(payload)


@pytest.mark.parametrize(
    "start,end",
    [
        ("0", "86400"),
        ("2026-09-07T00:00:00", "2026-09-08T00:00:00"),
        ("0001-01-01T00:00:00+01:00", "0001-01-02T00:00:00Z"),
    ],
)
def test_query_dates_require_representable_aware_iso_datetime(start, end):
    with pytest.raises(ValidationError):
        SummaryQuery.model_validate({"store_id": "s", "from": start, "to": end})


@pytest.mark.parametrize(
    "anchor,types",
    [
        ((True, "event"), (int, str)),
        ((1.5, "event"), (int, str)),
        ((0, "event"), (int, str)),
        ((1, ""), (int, str)),
        (("2026-09-07T00:00:00", "action"), (datetime, str)),
    ],
)
def test_cursor_rejects_invalid_typed_anchors(anchor, types):
    principal = TokenGrant(
        token="unit-test-credential-000001", principal_id="viewer", roles=["viewer"]
    )
    scope = read_scope(principal, "sales", store_id="s")
    with pytest.raises(AppError) as caught:
        decode_read_cursor(encode_read_cursor(scope, anchor), scope, types)
    assert caught.value.code == "INVALID_CURSOR"


def test_cursor_rechecks_authorization_and_normalizes_equivalent_dates():
    principal = TokenGrant(
        token="unit-test-credential-000001",
        principal_id="viewer",
        roles=["viewer"],
        store_ids=["s"],
    )
    scope = read_scope(
        principal, "sales", start=datetime.fromisoformat("2026-09-07T08:00:00+08:00")
    )
    token = encode_read_cursor(scope, (3, "event"))
    equivalent = read_scope(
        principal, "sales", start=datetime.fromisoformat("2026-09-07T00:00:00Z")
    )
    assert decode_read_cursor(token, equivalent, (int, str)) == (3, "event")
    principal.store_ids.append("other")
    with pytest.raises(AppError) as caught:
        decode_read_cursor(
            token,
            read_scope(principal, "sales", start=datetime.fromisoformat("2026-09-07T00:00:00Z")),
            (int, str),
        )
    assert caught.value.code == "INVALID_CURSOR"
