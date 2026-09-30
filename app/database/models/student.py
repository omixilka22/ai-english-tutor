from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    teacher_id: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id"),
        nullable=True,
    )
    reminders_enabled = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    meeting_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)

    level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
