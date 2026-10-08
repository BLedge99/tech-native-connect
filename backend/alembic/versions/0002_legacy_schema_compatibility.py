"""Upgrade databases created by the early demo branch.

The early prototype recorded itself as revision ``0001``.  Alembic accepts
that as the unique prefix of ``0001_initial``, so it cannot know that the
prototype's schema omitted a few columns later added to the initial schema.
This migration fills that gap without resetting developer data.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_legacy_schema_compatibility"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    inspector = sa.inspect(op.get_bind())

    def has_column(table: str, column: str) -> bool:
        return column in {item["name"] for item in inspector.get_columns(table)}

    def has_index(table: str, name: str) -> bool:
        return name in {item["name"] for item in inspector.get_indexes(table)}

    # The legacy seed reads these models back immediately, so the timestamp
    # columns must be present before it can seed or repair reference data.
    for table in ("courses", "skills", "interests"):
        if not has_column(table, "created_at"):
            op.add_column(
                table,
                sa.Column("created_at", timestamp, nullable=False, server_default=sa.text("now()")),
            )

    # Replace the old functional pair index with persisted normalized values.
    # This gives the current connection service a stable, race-safe lookup key.
    needs_pair_columns = not has_column("connection_requests", "pair_lo")
    if needs_pair_columns:
        op.add_column("connection_requests", sa.Column("pair_lo", postgresql.UUID(as_uuid=True), nullable=True))
        op.add_column("connection_requests", sa.Column("pair_hi", postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(
            "UPDATE connection_requests "
            "SET pair_lo = LEAST(sender_id, receiver_id), "
            "pair_hi = GREATEST(sender_id, receiver_id)"
        )
        op.alter_column("connection_requests", "pair_lo", nullable=False)
        op.alter_column("connection_requests", "pair_hi", nullable=False)
    if has_index("connection_requests", "one_request_per_pair"):
        op.drop_index("one_request_per_pair", table_name="connection_requests")
    if not has_index("connection_requests", "uq_one_request_per_pair"):
        op.create_index("uq_one_request_per_pair", "connection_requests", ["pair_lo", "pair_hi"], unique=True)
    if not has_index("connection_requests", "ix_connection_requests_received"):
        op.create_index("ix_connection_requests_received", "connection_requests", ["receiver_id", "status"])
    if not has_index("connection_requests", "ix_connection_requests_sent"):
        op.create_index("ix_connection_requests_sent", "connection_requests", ["sender_id", "status"])

    if not has_column("notifications", "url"):
        op.add_column(
            "notifications",
            sa.Column("url", sa.String(length=300), nullable=False, server_default=sa.text("'/notifications'")),
        )
    if not has_index("notifications", "ix_notifications_user_read_created"):
        op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read_at", "created_at"])
    if not has_index("notifications", "ix_notifications_unread"):
        op.create_index(
            "ix_notifications_unread",
            "notifications",
            ["user_id", "created_at"],
            postgresql_where=sa.text("read_at IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_column("notifications", "url")

    op.drop_index("ix_connection_requests_sent", table_name="connection_requests")
    op.drop_index("ix_connection_requests_received", table_name="connection_requests")
    op.drop_index("uq_one_request_per_pair", table_name="connection_requests")
    op.create_index(
        "one_request_per_pair",
        "connection_requests",
        [sa.text("LEAST(sender_id, receiver_id)"), sa.text("GREATEST(sender_id, receiver_id)")],
        unique=True,
    )
    op.drop_column("connection_requests", "pair_hi")
    op.drop_column("connection_requests", "pair_lo")

    for table in ("interests", "skills", "courses"):
        op.drop_column(table, "created_at")
