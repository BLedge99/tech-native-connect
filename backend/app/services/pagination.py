import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from app.web import ApiError


def encode_datetime_cursor(created_at: datetime, row_id: UUID) -> str:
    data = json.dumps({"created_at": created_at.isoformat(), "id": str(row_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode_datetime_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        data = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(data)
        return datetime.fromisoformat(value["created_at"]), UUID(value["id"])
    except (binascii.Error, ValueError, TypeError, KeyError) as exc:
        raise ApiError(
            422,
            "validation_error",
            "The page cursor is invalid.",
            {"cursor": "Use a cursor from the previous page."},
        ) from exc


def encode_name_cursor(name: str, row_id: UUID) -> str:
    data = json.dumps({"name": name, "id": str(row_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode_name_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        data = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(data)
        return str(value["name"]), UUID(value["id"])
    except (binascii.Error, ValueError, TypeError, KeyError) as exc:
        raise ApiError(
            422,
            "validation_error",
            "The page cursor is invalid.",
            {"cursor": "Use a cursor from the previous page."},
        ) from exc
