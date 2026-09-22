"""create analysis persistence schema

Revision ID: 20260922_0001
Revises:
Create Date: 2026-09-22
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260922_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "word_cloud_analysis",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("scoring_version", sa.String(length=200), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("profile_result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "analysis_type IN ('COURSE', 'SOLDIER_CONCERN', 'MEDIA')",
            name="ck_word_cloud_analysis_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_word_cloud_analysis_status",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('auto', 'sync', 'async')",
            name="ck_word_cloud_analysis_execution_mode",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_word_cloud_analysis_status_created_at",
        "word_cloud_analysis",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_word_cloud_analysis_type_created_at",
        "word_cloud_analysis",
        ["analysis_type", "created_at"],
    )

    op.create_table(
        "analysis_document",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["word_cloud_analysis.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "document_id",
            name="uq_analysis_document_analysis_document_id",
        ),
    )
    op.create_index(
        "ix_analysis_document_analysis_id",
        "analysis_document",
        ["analysis_id"],
    )

    op.create_table(
        "analysis_keyword",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("canonical_text", sa.String(length=500), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("statistical_score", sa.Float(), nullable=False),
        sa.Column("semantic_score", sa.Float(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_analysis_keyword_coverage"),
        sa.CheckConstraint("frequency >= 0", name="ck_analysis_keyword_frequency_nonnegative"),
        sa.CheckConstraint("rank > 0", name="ck_analysis_keyword_rank_positive"),
        sa.ForeignKeyConstraint(["analysis_id"], ["word_cloud_analysis.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "rank", name="uq_analysis_keyword_analysis_rank"),
    )
    op.create_index("ix_analysis_keyword_analysis_id", "analysis_keyword", ["analysis_id"])
    op.create_index(
        "ix_analysis_keyword_analysis_score",
        "analysis_keyword",
        ["analysis_id", "final_score"],
    )

    op.create_table(
        "analysis_topic",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("prevalence", sa.Float(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_analysis_topic_coverage"),
        sa.CheckConstraint("prevalence >= 0 AND prevalence <= 1", name="ck_analysis_topic_prevalence"),
        sa.CheckConstraint("rank > 0", name="ck_analysis_topic_rank_positive"),
        sa.ForeignKeyConstraint(["analysis_id"], ["word_cloud_analysis.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "rank", name="uq_analysis_topic_analysis_rank"),
    )
    op.create_index("ix_analysis_topic_analysis_id", "analysis_topic", ["analysis_id"])

    op.create_table(
        "analysis_topic_keyword",
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("keyword_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.CheckConstraint("rank > 0", name="ck_analysis_topic_keyword_rank_positive"),
        sa.ForeignKeyConstraint(["keyword_id"], ["analysis_keyword.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["analysis_topic.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("topic_id", "keyword_id"),
    )


def downgrade() -> None:
    op.drop_table("analysis_topic_keyword")
    op.drop_index("ix_analysis_topic_analysis_id", table_name="analysis_topic")
    op.drop_table("analysis_topic")
    op.drop_index("ix_analysis_keyword_analysis_score", table_name="analysis_keyword")
    op.drop_index("ix_analysis_keyword_analysis_id", table_name="analysis_keyword")
    op.drop_table("analysis_keyword")
    op.drop_index("ix_analysis_document_analysis_id", table_name="analysis_document")
    op.drop_table("analysis_document")
    op.drop_index("ix_word_cloud_analysis_type_created_at", table_name="word_cloud_analysis")
    op.drop_index("ix_word_cloud_analysis_status_created_at", table_name="word_cloud_analysis")
    op.drop_table("word_cloud_analysis")
