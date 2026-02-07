"""add_comment_conversation_link

Revision ID: 9c1a2b3d4e5f
Revises: 6a3b8d5c2e1f
Create Date: 2026-02-07 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c1a2b3d4e5f"
down_revision: str | Sequence[str] | None = "6a3b8d5c2e1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("comments") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f("ix_comments_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_comments_conversation_id_conversations",
            "conversations",
            ["conversation_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("comments") as batch_op:
        batch_op.drop_constraint("fk_comments_conversation_id_conversations", type_="foreignkey")
        batch_op.drop_index(op.f("ix_comments_conversation_id"))
        batch_op.drop_column("conversation_id")
