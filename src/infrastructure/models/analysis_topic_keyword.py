from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.context.sql_db.psql_dbcontext import Base

if TYPE_CHECKING:
    from src.infrastructure.models.analysis_keyword import AnalysisKeyword
    from src.infrastructure.models.analysis_topic import AnalysisTopic


class AnalysisTopicKeyword(Base):
    __tablename__ = "analysis_topic_keyword"
    __table_args__ = (
        CheckConstraint("rank > 0", name="ck_analysis_topic_keyword_rank_positive"),
    )

    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_topic.id", ondelete="CASCADE"), primary_key=True
    )
    keyword_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_keyword.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)

    topic: Mapped["AnalysisTopic"] = relationship(back_populates="keyword_links")
    keyword: Mapped["AnalysisKeyword"] = relationship(back_populates="topic_links")
