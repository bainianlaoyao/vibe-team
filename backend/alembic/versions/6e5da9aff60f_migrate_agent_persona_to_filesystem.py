"""migrate_agent_persona_to_filesystem

Revision ID: 6e5da9aff60f
Revises: 9c1a2b3d4e5f
Create Date: 2026-02-11 19:40:08.899200

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e5da9aff60f"
down_revision: str | Sequence[str] | None = "9c1a2b3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add new column (nullable initially)
    op.add_column("agents", sa.Column("persona_path", sa.String(length=512), nullable=True))

    # 2. Migrate data: Export personas to files
    from pathlib import Path

    connection = op.get_bind()

    # Use try-except to handle cases where tables might not exist
    # or schema is different during dry runs
    try:
        # Select existing agents
        agents = connection.execute(
            sa.text("SELECT id, project_id, name, initial_persona_prompt FROM agents")
        ).fetchall()

        for agent_id, project_id, name, persona_prompt in agents:
            # Get project root_path
            project = connection.execute(
                sa.text(f"SELECT root_path FROM projects WHERE id = {project_id}")
            ).fetchone()

            if project and persona_prompt:
                root_path = project[0]
                # Sanitize name for filename
                sanitized_name = (
                    name.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
                )
                persona_filename = f"{sanitized_name}.md"
                persona_rel_path = f"docs/agents/{persona_filename}"
                persona_full_path = Path(root_path) / persona_rel_path

                # Create directory and write file
                try:
                    persona_full_path.parent.mkdir(parents=True, exist_ok=True)
                    # Only write if file doesn't exist to avoid overwriting manual changes
                    # if run multiple times
                    if not persona_full_path.exists():
                        persona_full_path.write_text(persona_prompt, encoding="utf-8")
                        print(f"Migrated persona for '{name}' to {persona_rel_path}")

                    # Update database record
                    connection.execute(
                        sa.text("UPDATE agents SET persona_path = :path WHERE id = :id").bindparams(
                            path=persona_rel_path, id=agent_id
                        )
                    )
                except Exception as e:
                    print(f"Warning: Failed to migrate persona for agent {agent_id} ({name}): {e}")
    except Exception as e:
        print(f"Warning: Data migration skipped or failed: {e}")

    # 3. Drop old column
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("initial_persona_prompt")

    # 4. Other auto-generated changes
    op.drop_index(op.f("ix_inbox_items_resolver"), table_name="inbox_items")


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Restore index
    op.create_index(op.f("ix_inbox_items_resolver"), "inbox_items", ["resolver"], unique=False)

    # 2. Add back old column
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("initial_persona_prompt", sa.TEXT(), nullable=True))

    # 3. Restore data from files
    from pathlib import Path

    connection = op.get_bind()

    try:
        agents = connection.execute(
            sa.text(
                "SELECT id, project_id, persona_path FROM agents " "WHERE persona_path IS NOT NULL"
            )
        ).fetchall()

        for agent_id, project_id, persona_path in agents:
            project = connection.execute(
                sa.text(f"SELECT root_path FROM projects WHERE id = {project_id}")
            ).fetchone()

            if project:
                root_path = project[0]
                persona_full_path = Path(root_path) / persona_path

                if persona_full_path.exists():
                    try:
                        content = persona_full_path.read_text(encoding="utf-8")
                        connection.execute(
                            sa.text(
                                "UPDATE agents SET initial_persona_prompt = :content "
                                "WHERE id = :id"
                            ).bindparams(content=content, id=agent_id)
                        )
                    except Exception as e:
                        print(f"Warning: Failed to restore persona for agent {agent_id}: {e}")
    except Exception as e:
        print(f"Warning: Data restoration skipped or failed: {e}")

    # 4. Drop new column
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("persona_path")
