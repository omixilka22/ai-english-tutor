from datetime import datetime , timezone
from enum import Enum

from sqlalchemy import DateTime, Date, Boolean, Integer, String, Index, func, UniqueConstraint, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LessonStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    SENT = "sent"
    CANCELLED = "cancelled"


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("schedule_id", "occurrence_week", name="uq_lesson_schedule_week"),
                      Index("ix_lessons_student_time", "student_id", "scheduled_at"))

    notification_version = mapped_column(Integer, nullable=False, default=1, server_default="1")
    notification_since = mapped_column(DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now())

    is_deleted = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    conducted_at = mapped_column(DateTime(timezone=True), nullable=True)
    conducted_by = mapped_column(ForeignKey("teachers.id"), nullable=True)

    occurrence_week = mapped_column(Date, nullable=True)
    duration_minutes = mapped_column(Integer, nullable=False, default=60, server_default="60")
    timezone = mapped_column(String(64), nullable=False, default="Europe/Kyiv", server_default="Europe/Kyiv")
    is_exception = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    id: Mapped[int] = mapped_column(primary_key=True)

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"),
        nullable=False,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"),
        nullable=False,
    )

    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_schedules.id"),
        nullable=True,
    )

    scheduled_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[LessonStatus] = mapped_column(
        SQLEnum(LessonStatus),
        default=LessonStatus.SCHEDULED,
        nullable=False,
    )

    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
