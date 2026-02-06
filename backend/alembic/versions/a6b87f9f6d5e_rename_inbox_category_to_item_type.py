"""rename_inbox_category_to_item_type

Revision ID: a6b87f9f6d5e
Revises: 2f7f0d2795d4
Create Date: 2026-02-06 19:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b87f9f6d5e"
down_revision: str | Sequence[str] | None = "2f7f0d2795d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_index("ix_inbox_items_category", table_name="inbox_items")
    op.alter_column(
        "inbox_items",
        "category",
        existing_type=sa.String(length=32),
        new_column_name="item_type",
    )
    op.create_index("ix_inbox_items_item_type", "inbox_items", ["item_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_inbox_items_item_type", table_name="inbox_items")
    op.alter_column(
        "inbox_items",
        "item_type",
        existing_type=sa.String(length=32),
        new_column_name="category",
    )
    op.create_index("ix_inbox_items_category", "inbox_items", ["category"], unique=False)
