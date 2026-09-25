from datetime import datetime , timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LessonStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    SENT = "sent"


class Lesson(Base):
    __tablename__ = "lessons"

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