from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserRole(str, Enum):
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole),nullable=False)
    name: Mapped[str] = mapped_column( String(255), nullable=False)
    material_notice_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column( DateTime, default=datetime.utcnow,nullable=False)