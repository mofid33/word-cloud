from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.context.sql_db.psql_dbcontext import Base

if TYPE_CHECKING:
    from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
    from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis


class AnalysisKeyword(Base):
    __tablename__ = "analysis_keyword"
    __table_args__ = (
        UniqueConstraint("analysis_id", "rank", name="uq_analysis_keyword_analysis_rank"),
        CheckConstraint("rank > 0", name="ck_analysis_keyword_rank_positive"),
        CheckConstraint("frequency >= 0", name="ck_analysis_keyword_frequency_nonnegative"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="ck_analysis_keyword_coverage"),
        Index("ix_analysis_keyword_analysis_id", "analysis_id"),
        Index("ix_analysis_keyword_analysis_score", "analysis_id", "final_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("word_cloud_analysis.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_text: Mapped[str] = mapped_column(String(500), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    statistical_score: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False)

    analysis: Mapped["WordCloudAnalysis"] = relationship(back_populates="keywords")
    topic_links: Mapped[list["AnalysisTopicKeyword"]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan", passive_deletes=True
    )
