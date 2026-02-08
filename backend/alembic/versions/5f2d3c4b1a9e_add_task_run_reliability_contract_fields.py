"""add_task_run_reliability_contract_fields

Revision ID: 5f2d3c4b1a9e
Revises: 4d1ebd0789a5
Create Date: 2026-02-07 02:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f2d3c4b1a9e"
down_revision: str | Sequence[str] | None = "4d1ebd0789a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_index(
        op.f("ix_task_runs_next_retry_at"),
        "task_runs",
        ["next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_task_runs_next_retry_at"), table_name="task_runs")
