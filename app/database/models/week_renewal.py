from datetime import date
from sqlalchemy import Date, ForeignKey, String, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class WeekRenewal(Base):
    __tablename__ = 'week_renewals'
    __table_args__ = (UniqueConstraint('teacher_id', 'week_start', name='uq_teacher_week_renewal'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('teachers.id'), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default='pending', server_default='pending')
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
