from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, JSON, String, Integer, Boolean, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AnalysisStatus(str, Enum):
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"


class LessonAnalysis(Base):
    __tablename__ = "lesson_analyses"
    __table_args__ = (Index("ix_analysis_workflow", "workflow_state", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id"),
        unique=True,
        nullable=False,
    )

    status: Mapped[AnalysisStatus] = mapped_column(
        SQLEnum(AnalysisStatus),
        default=AnalysisStatus.PROCESSING,
        nullable=False,
    )

    content: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    workflow_state = mapped_column(String(24), nullable=False, default='legacy', server_default='legacy')
    revision = mapped_column(Integer, nullable=False, default=1, server_default='1')
    last_error = mapped_column(String(64), nullable=True)
    attempts = mapped_column(Integer, nullable=False, default=0, server_default='0')
    next_attempt_at = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id = mapped_column(BigInteger, nullable=True)
    review_notified = mapped_column(Boolean, nullable=False, default=False, server_default='false')

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )