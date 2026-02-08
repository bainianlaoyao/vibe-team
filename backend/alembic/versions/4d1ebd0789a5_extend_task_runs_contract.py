"""extend_task_runs_contract

Revision ID: 4d1ebd0789a5
Revises: a6b87f9f6d5e
Create Date: 2026-02-07 02:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d1ebd0789a5"
down_revision: str | Sequence[str] | None = "a6b87f9f6d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("task_runs") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE task_runs SET idempotency_key = lower(hex(randomblob(16)))")

    with op.batch_alter_table("task_runs") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(length=80),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_task_runs_idempotency_key",
            ["idempotency_key"],
        )
        batch_op.create_check_constraint(
            "ck_task_runs_idempotency_key_present",
            "length(idempotency_key) >= 1",
        )
        batch_op.create_check_constraint(
            "ck_task_runs_next_retry_status_match",
            "next_retry_at IS NULL OR run_status = 'retry_scheduled'",
        )
        batch_op.create_check_constraint(
            "ck_task_runs_retry_status_requires_next_retry_at",
            "run_status <> 'retry_scheduled' OR next_retry_at IS NOT NULL",
        )
        batch_op.create_index(
            "ix_task_runs_retry_schedule",
            ["run_status", "next_retry_at"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("task_runs") as batch_op:
        batch_op.drop_index("ix_task_runs_retry_schedule")
        batch_op.drop_constraint(
            "ck_task_runs_retry_status_requires_next_retry_at",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_task_runs_next_retry_status_match",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_task_runs_idempotency_key_present",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_task_runs_idempotency_key",
            type_="unique",
        )
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("idempotency_key")
