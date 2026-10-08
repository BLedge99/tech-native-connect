"""Postgres enum types. The database refuses values outside these.

See specs/03_profiles.md §3 — using a real enum rather than varchar + CHECK
means an invalid role cannot reach the database even if a route has a bug.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ENUM

import enum


class UserRole(enum.StrEnum):
    SOFTWARE_DEVELOPER = "software_developer"
    BUSINESS_DEVELOPER = "business_developer"


class ConnectionStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class NotificationType(enum.StrEnum):
    CONNECTION_REQUESTED = "connection_requested"
    CONNECTION_ACCEPTED = "connection_accepted"
    CONNECTION_DECLINED = "connection_declined"
    NEW_MESSAGE = "new_message"
    IDEA_INTEREST = "idea_interest"


class IdeaCategory(enum.StrEnum):
    FIND_PROBLEM = "find_problem"
    BUILD_PRODUCT = "build_product"
    DESIGN_BRAND = "design_brand"
    RUN_CAMPAIGN = "run_campaign"
    OTHER = "other"


def pg_enum(py_enum: type[enum.StrEnum], name: str) -> ENUM:
    return ENUM(
        py_enum,
        name=name,
        # Migrations create the type explicitly; don't emit a duplicate CREATE.
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


user_role_enum = pg_enum(UserRole, "user_role")
connection_status_enum = pg_enum(ConnectionStatus, "connection_status")
notification_type_enum = pg_enum(NotificationType, "notification_type")
idea_category_enum = pg_enum(IdeaCategory, "idea_category")

__all__ = [
    "UserRole",
    "ConnectionStatus",
    "NotificationType",
    "IdeaCategory",
    "user_role_enum",
    "connection_status_enum",
    "notification_type_enum",
    "idea_category_enum",
]