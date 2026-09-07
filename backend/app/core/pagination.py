import base64
import json
from datetime import datetime

from app.core.errors import AppError
from app.core.hashing import digest


def encode_cursor(scope, row):
    data = {"scope": digest(scope), "at": row.created_at.isoformat(), "id": row.id}
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor, scope):
    if cursor is None:
        return None
    try:
        if len(cursor) > 2048:
            raise ValueError()
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        timestamp = datetime.fromisoformat(value["at"])
        if value["scope"] != digest(scope) or timestamp.tzinfo is None:
            raise ValueError()
        if not isinstance(value["id"], str) or not 1 <= len(value["id"]) <= 128:
            raise ValueError()
        return timestamp, value["id"]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise AppError(422, "INVALID_CURSOR", "Cursor is invalid for this query") from exc
