from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.orm import mapped_column
from app.database.base import Base


class LessonNotification(Base):
    __tablename__ = 'lesson_notifications'
    __table_args__ = (
        UniqueConstraint('lesson_id','revision','kind','student_id',name='uq_lesson_notification'),
        Index('ix_notifications_pending','status','next_attempt_at'),
    )
    id = mapped_column(Integer,primary_key=True)
    lesson_id = mapped_column(ForeignKey('lessons.id'),nullable=False)
    student_id = mapped_column(ForeignKey('students.id'),nullable=False)
    revision = mapped_column(Integer,nullable=False)
    kind = mapped_column(String(32),nullable=False)
    status = mapped_column(String(16),nullable=False,default='pending',server_default='pending')
    due_at = mapped_column(DateTime(timezone=True),nullable=False)
    expires_at = mapped_column(DateTime(timezone=True),nullable=False)
    next_attempt_at = mapped_column(DateTime(timezone=True),nullable=False)
    attempts = mapped_column(Integer,nullable=False,default=0,server_default='0')
    sent_at = mapped_column(DateTime(timezone=True),nullable=True)
    telegram_message_id = mapped_column(BigInteger,nullable=True)
    last_error = mapped_column(String(128),nullable=True)
    created_at = mapped_column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
