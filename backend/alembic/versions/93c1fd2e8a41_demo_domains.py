"""Add profiles, matching, collaboration, ideas, and admin domains."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "93c1fd2e8a41"
down_revision = "4f98c1b7e2a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in (
        ("user_role", ("software_developer", "business_developer")),
        ("connection_status", ("pending", "accepted", "declined")),
        (
            "notification_type",
            ("connection_requested", "connection_accepted", "connection_declined", "new_message", "idea_interest"),
        ),
        ("idea_category", ("find_problem", "build_product", "design_brand", "run_campaign", "other")),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    uuid = sa.UUID()
    created_at = sa.DateTime(timezone=True)
    op.create_table(
        "courses",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "skills",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("category", sa.String(50)),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "interests",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "photos",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("byte_size <= 2097152", name="ck_photos_max_size"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("bio", sa.String(500)),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False)),
        sa.Column("course_id", uuid, sa.ForeignKey("courses.id", ondelete="SET NULL")),
        sa.Column("looking_for", sa.String(300)),
        sa.Column("photo_id", uuid, sa.ForeignKey("photos.id", ondelete="SET NULL")),
        sa.Column("profile_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_profiles_profile_complete", "profiles", ["profile_complete"])
    op.create_table(
        "profile_skills",
        sa.Column("profile_id", uuid, sa.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", uuid, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "profile_interests",
        sa.Column("profile_id", uuid, sa.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("interest_id", uuid, sa.ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "connection_requests",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sender_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receiver_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="connection_status", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("message", sa.String(300)),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
        sa.Column("responded_at", created_at),
        sa.Column("responded_by", uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("sender_id <> receiver_id", name="ck_connection_not_self"),
    )
    op.create_index("ix_connections_receiver_status", "connection_requests", ["receiver_id", "status"])
    op.create_index("ix_connections_sender_status", "connection_requests", ["sender_id", "status"])
    op.execute(
        "CREATE UNIQUE INDEX uq_connection_pair ON connection_requests "
        "(LEAST(sender_id, receiver_id), GREATEST(sender_id, receiver_id))"
    )
    op.create_table(
        "threads",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "connection_request_id",
            uuid,
            sa.ForeignKey("connection_requests.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "messages",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", uuid, sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_thread_created_id", "messages", ["thread_id", "created_at", "id"])
    op.create_table(
        "read_receipts",
        sa.Column("thread_id", uuid, sa.ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_read_at", created_at, nullable=False),
    )
    op.create_table(
        "project_ideas",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("author_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", postgresql.ENUM(name="idea_category", create_type=False), nullable=False),
        sa.Column("skills_needed", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'::varchar[]")),
        sa.Column("course_id", uuid, sa.ForeignKey("courses.id", ondelete="SET NULL")),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_project_ideas_created", "project_ideas", ["created_at"])
    op.create_index("ix_project_ideas_author", "project_ideas", ["author_id"])
    op.create_index("ix_project_ideas_open_created", "project_ideas", ["is_open", "created_at"])
    op.create_table(
        "idea_interests",
        sa.Column("idea_id", uuid, sa.ForeignKey("project_ideas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "notifications",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", postgresql.ENUM(name="notification_type", create_type=False), nullable=False),
        sa.Column("actor_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("connection_request_id", uuid, sa.ForeignKey("connection_requests.id", ondelete="SET NULL")),
        sa.Column("thread_id", uuid, sa.ForeignKey("threads.id", ondelete="SET NULL")),
        sa.Column("project_idea_id", uuid, sa.ForeignKey("project_ideas.id", ondelete="SET NULL")),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", created_at),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read_at", "created_at"])
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "admin_audit_log",
        sa.Column("id", uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("admin_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50)),
        sa.Column("target_id", uuid),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", created_at, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_created", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_admin_created", "admin_audit_log", ["admin_id", "created_at"])


def downgrade() -> None:
    for table in (
        "admin_audit_log",
        "notifications",
        "idea_interests",
        "project_ideas",
        "read_receipts",
        "messages",
        "threads",
        "connection_requests",
        "profile_interests",
        "profile_skills",
        "profiles",
        "photos",
        "interests",
        "skills",
        "courses",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for name in ("idea_category", "notification_type", "connection_status", "user_role"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
