"""approval_requests table (Priority 4: persistent approvals)

Revision ID: d5e8f2a7b3c1
Revises: c3d7e1a9f2b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e8f2a7b3c1"
down_revision: Union[str, None] = "c3d7e1a9f2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=512), nullable=True),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CONSUMED', 'EXPIRED')",
            name="ck_approval_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_status", "approval_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_approval_status", table_name="approval_requests")
    op.drop_table("approval_requests")
