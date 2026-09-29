from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.context.sql_db.psql_dbcontext import Base


class AnalysisQueueJobModel(Base):
    __tablename__ = "analysis_queue_job"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'leased')",
            name="ck_analysis_queue_job_state",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_analysis_queue_job_attempt_count",
        ),
        UniqueConstraint(
            "analysis_id",
            name="uq_analysis_queue_job_analysis_id",
        ),
        Index(
            "ix_analysis_queue_job_available",
            "state",
            "available_at",
            "created_at",
        ),
        Index(
            "ix_analysis_queue_job_lease_expiry",
            "state",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("word_cloud_analysis.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
