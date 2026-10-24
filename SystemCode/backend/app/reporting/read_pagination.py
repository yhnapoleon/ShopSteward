"""Typed seek cursors for the frontend read views; authorization stays in SQL."""

import base64
import json
from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.hashing import digest


def read_scope(principal, kind, **filters):
    return {
        "kind": kind,
        "principal": principal.principal_id,
        "roles": sorted(set(principal.roles)),
        "stores": sorted(set(principal.store_ids)),
        "filters": {
            key: value.astimezone(UTC).isoformat() if isinstance(value, datetime) else value
            for key, value in filters.items()
        },
    }


def encode_read_cursor(scope, anchor):
    value = {
        "v": 1,
        "kind": scope["kind"],
        "scope": digest(scope),
        "anchor": [
            item.astimezone(UTC).isoformat() if isinstance(item, datetime) else item
            for item in anchor
        ],
    }
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()


def decode_read_cursor(cursor, scope, key_types):
    if cursor is None:
        return None
    try:
        if not 1 <= len(cursor) <= 2048:
            raise ValueError()
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(value, dict) or set(value) != {"v", "kind", "scope", "anchor"}:
            raise ValueError()
        if (
            type(value["v"]) is not int
            or value["v"] != 1
            or value["kind"] != scope["kind"]
            or value["scope"] != digest(scope)
        ):
            raise ValueError()
        raw = value["anchor"]
        if not isinstance(raw, list) or len(raw) != len(key_types):
            raise ValueError()
        result = []
        for item, kind in zip(raw, key_types, strict=True):
            if kind is datetime:
                if not isinstance(item, str):
                    raise ValueError()
                item = datetime.fromisoformat(item)
                if item.tzinfo is None or item.utcoffset() is None:
                    raise ValueError()
                item = item.astimezone(UTC)
            elif kind is str:
                if not isinstance(item, str) or not 1 <= len(item) <= 128:
                    raise ValueError()
            elif kind is int:
                if type(item) is not int or not 1 <= item <= 2**63 - 1:
                    raise ValueError()
            else:
                raise ValueError()
            result.append(item)
        return tuple(result)
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
        raise AppError(422, "INVALID_CURSOR", "Cursor is invalid for this query") from exc
