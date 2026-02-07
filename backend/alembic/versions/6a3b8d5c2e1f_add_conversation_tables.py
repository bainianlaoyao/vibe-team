"""add_conversation_tables

Revision ID: 6a3b8d5c2e1f
Revises: 5f2d3c4b1a9e
Create Date: 2026-02-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a3b8d5c2e1f"
down_revision: str | Sequence[str] | None = "5f2d3c4b1a9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create conversations, messages, and conversation_sessions tables."""

    # Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_conversations_version_positive"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversations_project_id"), "conversations", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_conversations_agent_id"), "conversations", ["agent_id"], unique=False)
    op.create_index(op.f("ix_conversations_task_id"), "conversations", ["task_id"], unique=False)
    op.create_index(op.f("ix_conversations_title"), "conversations", ["title"], unique=False)
    op.create_index(op.f("ix_conversations_status"), "conversations", ["status"], unique=False)
    op.create_index(
        op.f("ix_conversations_created_at"), "conversations", ["created_at"], unique=False
    )
    op.create_index(
        "ix_conversations_project_status", "conversations", ["project_id", "status"], unique=False
    )
    op.create_index(
        "ix_conversations_agent_created", "conversations", ["agent_id", "created_at"], unique=False
    )

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("sequence_num", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_messages_role"), "messages", ["role"], unique=False)
    op.create_index(op.f("ix_messages_message_type"), "messages", ["message_type"], unique=False)
    op.create_index(op.f("ix_messages_sequence_num"), "messages", ["sequence_num"], unique=False)
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False)
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_messages_conversation_sequence",
        "messages",
        ["conversation_id", "sequence_num"],
        unique=False,
    )

    # Create conversation_sessions table
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("last_message_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["last_message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "client_id", name="uq_conversation_sessions_conv_client"
        ),
    )
    op.create_index(
        op.f("ix_conversation_sessions_conversation_id"),
        "conversation_sessions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_sessions_client_id"),
        "conversation_sessions",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_sessions_status"), "conversation_sessions", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_conversation_sessions_last_heartbeat_at"),
        "conversation_sessions",
        ["last_heartbeat_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_sessions_status_heartbeat",
        "conversation_sessions",
        ["status", "last_heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop conversations, messages, and conversation_sessions tables."""

    op.drop_index("ix_conversation_sessions_status_heartbeat", table_name="conversation_sessions")
    op.drop_index(
        op.f("ix_conversation_sessions_last_heartbeat_at"), table_name="conversation_sessions"
    )
    op.drop_index(op.f("ix_conversation_sessions_status"), table_name="conversation_sessions")
    op.drop_index(op.f("ix_conversation_sessions_client_id"), table_name="conversation_sessions")
    op.drop_index(
        op.f("ix_conversation_sessions_conversation_id"), table_name="conversation_sessions"
    )
    op.drop_table("conversation_sessions")

    op.drop_index("ix_messages_conversation_sequence", table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_sequence_num"), table_name="messages")
    op.drop_index(op.f("ix_messages_message_type"), table_name="messages")
    op.drop_index(op.f("ix_messages_role"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_agent_created", table_name="conversations")
    op.drop_index("ix_conversations_project_status", table_name="conversations")
    op.drop_index(op.f("ix_conversations_created_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_status"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_title"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_task_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_agent_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_project_id"), table_name="conversations")
    op.drop_table("conversations")
