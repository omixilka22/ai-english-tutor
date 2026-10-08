from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import mapped_column
from app.database.base import Base


class RecallSession(Base):
    __tablename__ = 'recall_sessions'
    id = mapped_column(String(36), primary_key=True)
    lesson_id = mapped_column(ForeignKey('lessons.id'), unique=True, nullable=False)
    bot_id = mapped_column(String(36), unique=True, nullable=True)
    recording_id = mapped_column(String(36), unique=True, nullable=True)
    transcript_id = mapped_column(String(36), unique=True, nullable=True)
    meeting_url = mapped_column(String(255), nullable=True)
    state = mapped_column(String(32), nullable=False)
    error = mapped_column(String(64), nullable=True)
    attempts = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at = mapped_column(DateTime(timezone=True), nullable=True)
    stop_at = mapped_column(DateTime(timezone=True), nullable=False)
    leave_requested = mapped_column(Boolean, nullable=False, default=False)
    leave_sent = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    cleanup_state = mapped_column(String(20), nullable=False, default='none')
    cleanup_after = mapped_column(DateTime(timezone=True), nullable=True)
    notice_sent = mapped_column(Boolean, nullable=False, default=False)


class RecallEvent(Base):
    __tablename__ = 'recall_events'
    id = mapped_column(String(255), primary_key=True)
    event = mapped_column(String(64), nullable=False)
    bot_id = mapped_column(String(36), nullable=False)
    session_id = mapped_column(String(36), nullable=True)
    recording_id = mapped_column(String(36), nullable=True)
    transcript_id = mapped_column(String(36), nullable=True)
    done = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False)
