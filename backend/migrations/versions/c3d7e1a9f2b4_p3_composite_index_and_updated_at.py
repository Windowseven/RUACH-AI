"""messages: composite index + conversations.updated_at (Priority 3)

Deterministic ordering needs an index that matches the access pattern
(conversation_id, seq); conversation freshness needs updated_at.

Revision ID: c3d7e1a9f2b4
Revises: a1f9c2d4e5b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d7e1a9f2b4"
down_revision: Union[str, None] = "a1f9c2d4e5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_conversation_seq", "messages", ["conversation_id", "seq"]
    )
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now())
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("updated_at")
    op.drop_index("ix_messages_conversation_seq", table_name="messages")
