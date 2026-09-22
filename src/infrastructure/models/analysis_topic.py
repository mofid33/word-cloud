from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.context.sql_db.psql_dbcontext import Base

if TYPE_CHECKING:
    from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
    from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis


class AnalysisTopic(Base):
    __tablename__ = "analysis_topic"
    __table_args__ = (
        UniqueConstraint("analysis_id", "rank", name="uq_analysis_topic_analysis_rank"),
        CheckConstraint("rank > 0", name="ck_analysis_topic_rank_positive"),
        CheckConstraint("prevalence >= 0 AND prevalence <= 1", name="ck_analysis_topic_prevalence"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_analysis_topic_coverage"),
        Index("ix_analysis_topic_analysis_id", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("word_cloud_analysis.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    prevalence: Mapped[float] = mapped_column(Float, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    analysis: Mapped["WordCloudAnalysis"] = relationship(back_populates="topics")
    keyword_links: Mapped[list["AnalysisTopicKeyword"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", passive_deletes=True
    )
