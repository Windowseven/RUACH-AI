"""messages.seq for stable ordering within a conversation

Revision ID: a1f9c2d4e5b7
Revises: e384b7713ab9
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f9c2d4e5b7"
down_revision: Union[str, None] = "e384b7713ab9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(
            sa.Column("seq", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("seq")
