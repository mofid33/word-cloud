from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.context.sql_db.psql_dbcontext import Base

if TYPE_CHECKING:
    from src.infrastructure.models.analysis_document import AnalysisDocument
    from src.infrastructure.models.analysis_keyword import AnalysisKeyword
    from src.infrastructure.models.analysis_topic import AnalysisTopic


class WordCloudAnalysis(Base):
    __tablename__ = "word_cloud_analysis"
    __table_args__ = (
        CheckConstraint(
            "analysis_type IN ('COURSE', 'SOLDIER_CONCERN', 'MEDIA')",
            name="ck_word_cloud_analysis_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_word_cloud_analysis_status",
        ),
        CheckConstraint(
            "execution_mode IN ('auto', 'sync', 'async')",
            name="ck_word_cloud_analysis_execution_mode",
        ),
        Index("ix_word_cloud_analysis_status_created_at", "status", "created_at"),
        Index("ix_word_cloud_analysis_type_created_at", "analysis_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    profile_result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["AnalysisDocument"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )
    keywords: Mapped[list["AnalysisKeyword"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )
    topics: Mapped[list["AnalysisTopic"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )
