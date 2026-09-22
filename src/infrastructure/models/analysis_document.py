from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.context.sql_db.psql_dbcontext import Base

if TYPE_CHECKING:
    from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis


class AnalysisDocument(Base):
    __tablename__ = "analysis_document"
    __table_args__ = (
        UniqueConstraint("analysis_id", "document_id", name="uq_analysis_document_analysis_document_id"),
        Index("ix_analysis_document_analysis_id", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("word_cloud_analysis.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis: Mapped["WordCloudAnalysis"] = relationship(back_populates="documents")
