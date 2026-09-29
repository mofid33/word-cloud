"""add durable analysis queue

Revision ID: 20260929_0002
Revises: 20260922_0001
Create Date: 2026-09-29
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260929_0002"
down_revision: str | Sequence[str] | None = "20260922_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_queue_job",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "modified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'leased')",
            name="ck_analysis_queue_job_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_analysis_queue_job_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["word_cloud_analysis.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            name="uq_analysis_queue_job_analysis_id",
        ),
    )
    op.create_index(
        "ix_analysis_queue_job_available",
        "analysis_queue_job",
        ["state", "available_at", "created_at"],
    )
    op.create_index(
        "ix_analysis_queue_job_lease_expiry",
        "analysis_queue_job",
        ["state", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_queue_job_lease_expiry",
        table_name="analysis_queue_job",
    )
    op.drop_index(
        "ix_analysis_queue_job_available",
        table_name="analysis_queue_job",
    )
    op.drop_table("analysis_queue_job")
