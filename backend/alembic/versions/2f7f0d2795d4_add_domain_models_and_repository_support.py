"""add_domain_models_and_repository_support

Revision ID: 2f7f0d2795d4
Revises: 0b1a7dfc796f
Create Date: 2026-02-06 18:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f7f0d2795d4"
down_revision: str | Sequence[str] | None = "0b1a7dfc796f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_check_constraint("ck_projects_version_positive", "version >= 1")

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_unique_constraint("uq_agents_project_name", ["project_id", "name"])
        batch_op.create_check_constraint("ck_agents_version_positive", "version >= 1")

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_check_constraint("ck_tasks_priority_range", "priority BETWEEN 1 AND 5")
        batch_op.create_check_constraint("ck_tasks_version_positive", "version >= 1")

    op.create_index(
        "ix_tasks_project_status_priority",
        "tasks",
        ["project_id", "status", "priority"],
        unique=False,
    )

    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_task_id", sa.Integer(), nullable=False),
        sa.Column("dependency_type", sa.String(length=32), nullable=False),
        sa.CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependencies_not_self"),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"],
            ["tasks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
    )
    op.create_index(
        op.f("ix_task_dependencies_depends_on_task_id"),
        "task_dependencies",
        ["depends_on_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_dependencies_task_id"), "task_dependencies", ["task_id"], unique=False
    )

    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("run_status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("token_in", sa.Integer(), nullable=False),
        sa.Column("token_out", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempt >= 1", name="ck_task_runs_attempt_positive"),
        sa.CheckConstraint("cost_usd >= 0", name="ck_task_runs_cost_non_negative"),
        sa.CheckConstraint("token_in >= 0", name="ck_task_runs_token_in_non_negative"),
        sa.CheckConstraint("token_out >= 0", name="ck_task_runs_token_out_non_negative"),
        sa.CheckConstraint("version >= 1", name="ck_task_runs_version_positive"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt", name="uq_task_runs_task_attempt"),
    )
    op.create_index(op.f("ix_task_runs_agent_id"), "task_runs", ["agent_id"], unique=False)
    op.create_index(op.f("ix_task_runs_run_status"), "task_runs", ["run_status"], unique=False)
    op.create_index(op.f("ix_task_runs_started_at"), "task_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_task_runs_task_id"), "task_runs", ["task_id"], unique=False)
    op.create_index(
        "ix_task_runs_task_status_started",
        "task_runs",
        ["task_id", "run_status", "started_at"],
        unique=False,
    )

    op.create_table(
        "inbox_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolver", sa.String(length=120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_inbox_items_version_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inbox_items_category"), "inbox_items", ["category"], unique=False)
    op.create_index(op.f("ix_inbox_items_created_at"), "inbox_items", ["created_at"], unique=False)
    op.create_index(op.f("ix_inbox_items_project_id"), "inbox_items", ["project_id"], unique=False)
    op.create_index(
        "ix_inbox_items_project_status",
        "inbox_items",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_inbox_items_resolver"), "inbox_items", ["resolver"], unique=False)
    op.create_index(op.f("ix_inbox_items_source_id"), "inbox_items", ["source_id"], unique=False)
    op.create_index(
        op.f("ix_inbox_items_source_type"), "inbox_items", ["source_type"], unique=False
    )
    op.create_index(op.f("ix_inbox_items_status"), "inbox_items", ["status"], unique=False)
    op.create_index(op.f("ix_inbox_items_title"), "inbox_items", ["title"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_documents_version_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "path", name="uq_documents_project_path"),
    )
    op.create_index(op.f("ix_documents_doc_type"), "documents", ["doc_type"], unique=False)
    op.create_index(
        "ix_documents_project_doc_type",
        "documents",
        ["project_id", "doc_type"],
        unique=False,
    )
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_documents_title"), "documents", ["title"], unique=False)
    op.create_index(op.f("ix_documents_updated_at"), "documents", ["updated_at"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("anchor", sa.String(length=240), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(document_id IS NOT NULL) OR (task_id IS NOT NULL)",
            name="ck_comments_target_present",
        ),
        sa.CheckConstraint("version >= 1", name="ck_comments_version_positive"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comments_author"), "comments", ["author"], unique=False)
    op.create_index(op.f("ix_comments_created_at"), "comments", ["created_at"], unique=False)
    op.create_index(op.f("ix_comments_document_id"), "comments", ["document_id"], unique=False)
    op.create_index(op.f("ix_comments_status"), "comments", ["status"], unique=False)
    op.create_index(op.f("ix_comments_task_id"), "comments", ["task_id"], unique=False)

    op.create_table(
        "api_usage_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=False),
        sa.Column("token_out", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.CheckConstraint(
            "request_count >= 0", name="ck_api_usage_daily_request_count_non_negative"
        ),
        sa.CheckConstraint("token_in >= 0", name="ck_api_usage_daily_token_in_non_negative"),
        sa.CheckConstraint("token_out >= 0", name="ck_api_usage_daily_token_out_non_negative"),
        sa.CheckConstraint("cost_usd >= 0", name="ck_api_usage_daily_cost_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_name", "date", name="uq_api_usage_daily_dim"),
    )
    op.create_index(op.f("ix_api_usage_daily_date"), "api_usage_daily", ["date"], unique=False)
    op.create_index(
        op.f("ix_api_usage_daily_model_name"), "api_usage_daily", ["model_name"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_daily_provider"), "api_usage_daily", ["provider"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_api_usage_daily_provider"), table_name="api_usage_daily")
    op.drop_index(op.f("ix_api_usage_daily_model_name"), table_name="api_usage_daily")
    op.drop_index(op.f("ix_api_usage_daily_date"), table_name="api_usage_daily")
    op.drop_table("api_usage_daily")

    op.drop_index(op.f("ix_comments_task_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_status"), table_name="comments")
    op.drop_index(op.f("ix_comments_document_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_created_at"), table_name="comments")
    op.drop_index(op.f("ix_comments_author"), table_name="comments")
    op.drop_table("comments")

    op.drop_index(op.f("ix_documents_updated_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_title"), table_name="documents")
    op.drop_index(op.f("ix_documents_project_id"), table_name="documents")
    op.drop_index("ix_documents_project_doc_type", table_name="documents")
    op.drop_index(op.f("ix_documents_doc_type"), table_name="documents")
    op.drop_table("documents")

    op.drop_index(op.f("ix_inbox_items_title"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_status"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_source_type"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_source_id"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_resolver"), table_name="inbox_items")
    op.drop_index("ix_inbox_items_project_status", table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_project_id"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_created_at"), table_name="inbox_items")
    op.drop_index(op.f("ix_inbox_items_category"), table_name="inbox_items")
    op.drop_table("inbox_items")

    op.drop_index("ix_task_runs_task_status_started", table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_task_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_started_at"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_run_status"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_agent_id"), table_name="task_runs")
    op.drop_table("task_runs")

    op.drop_index(op.f("ix_task_dependencies_task_id"), table_name="task_dependencies")
    op.drop_index(op.f("ix_task_dependencies_depends_on_task_id"), table_name="task_dependencies")
    op.drop_table("task_dependencies")

    op.drop_index("ix_tasks_project_status_priority", table_name="tasks")

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint("ck_tasks_version_positive", type_="check")
        batch_op.drop_constraint("ck_tasks_priority_range", type_="check")
        batch_op.drop_column("version")

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_constraint("ck_agents_version_positive", type_="check")
        batch_op.drop_constraint("uq_agents_project_name", type_="unique")
        batch_op.drop_column("version")

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint("ck_projects_version_positive", type_="check")
        batch_op.drop_column("version")
