"""Import every model so Alembic autogenerate sees the full metadata."""

from app.db import Base
from app.models.connection import ConnectionRequest
from app.models.enums import (
    ConnectionStatus,
    IdeaCategory,
    NotificationType,
    UserRole,
    connection_status_enum,
    idea_category_enum,
    notification_type_enum,
    user_role_enum,
)
from app.models.idea import ProjectIdea, idea_interests
from app.models.notification import AdminAuditLog, Notification
from app.models.profile import (
    Course,
    Interest,
    Photo,
    Profile,
    Skill,
    profile_interests,
    profile_skills,
)
from app.models.thread import Message, ReadReceipt, Thread
from app.models.user import MagicLinkToken, Session, User

__all__ = [
    "Base",
    "User",
    "Session",
    "MagicLinkToken",
    "Profile",
    "Photo",
    "Course",
    "Skill",
    "Interest",
    "profile_skills",
    "profile_interests",
    "ConnectionRequest",
    "Thread",
    "Message",
    "ReadReceipt",
    "Notification",
    "AdminAuditLog",
    "ProjectIdea",
    "idea_interests",
    "UserRole",
    "ConnectionStatus",
    "NotificationType",
    "IdeaCategory",
    "user_role_enum",
    "connection_status_enum",
    "notification_type_enum",
    "idea_category_enum",
]