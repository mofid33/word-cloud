"""allow unbounded analysis model provenance

Revision ID: 20261005_0003
Revises: 20260929_0002
Create Date: 2026-10-05
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261005_0003"
down_revision: str | Sequence[str] | None = "20260929_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "word_cloud_analysis",
        "model_version",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "word_cloud_analysis",
        "model_version",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
        existing_nullable=True,
    )
