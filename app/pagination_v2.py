from __future__ import annotations

import base64
import json
from datetime import datetime, timezone


class InvalidCursorError(ValueError):
    pass


def encode_listing_cursor(*, created_at: datetime, listing_id: str) -> str:
    ts = created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    payload = {"created_at": ts.isoformat(), "id": listing_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_listing_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        created_at = datetime.fromisoformat(data["created_at"])
        listing_id = str(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("cursor is malformed") from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at, listing_id
