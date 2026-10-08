"""Cursor pagination. specs/00_conventions.md §5.

Offsets skip or duplicate rows when data changes between requests — exactly what
happens when someone sends a message during the demo. Every list endpoint uses
this so a row cannot appear on two pages.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.errors import BadRequest


def encode_cursor(sort_value: Any, tiebreaker: UUID) -> str:
    """Opaque to clients. Encoding the sort value plus its tiebreaker is what
    makes the ordering a total order — a fuzzy tiebreak lets page 2 repeat rows
    from page 1."""
    payload = {
        "v": sort_value.isoformat() if isinstance(sort_value, datetime) else sort_value,
        "u": str(tiebreaker),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime | float | int, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        value = payload["v"]
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValueError("Invalid cursor value")
        if isinstance(value, str) and ("-" in value and "T" in value):
            value = datetime.fromisoformat(value)
        return value, UUID(payload["u"])
    except (ValueError, TypeError, KeyError, OverflowError, binascii.Error) as exc:
        raise BadRequest("That pagination cursor is invalid.", code="invalid_cursor") from exc


def next_cursor_or_none(rows: list, limit: int, sort_of) -> str | None:
    """None when the page is the last one.

    Requires `limit + 1` rows to have been fetched, so a full page is only
    reported as "there is more" when there genuinely is.
    """
    if len(rows) < limit + 1:
        return None
    last = rows[limit - 1]
    return encode_cursor(sort_of(last), last.id)
