from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Student, TeacherInvite
from app.database.repository.teacher_invite_repository import (
    TeacherInviteRepository,
)


class InviteService:

    @staticmethod
    async def get_by_token(
        session: AsyncSession,
        token: str,
    ) -> TeacherInvite | None:
        return await TeacherInviteRepository.get_by_token(
            session,
            token,
        )

    @staticmethod
    async def create_invite(
        session: AsyncSession,
        teacher_id: int,
        expires_in_hours: int = 24,
    ) -> TeacherInvite:
        token = token_urlsafe(32)

        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=expires_in_hours
        )

        return await TeacherInviteRepository.create(
            session,
            teacher_id,
            token,
            expires_at,
        )

    @staticmethod
    async def validate_invite(
        session: AsyncSession,
        token: str,
    ) -> TeacherInvite:
        invite = await TeacherInviteRepository.get_by_token(
            session,
            token,
        )

        if invite is None:
            raise ValueError("Invite not found")

        if invite.used_at is not None:
            raise ValueError("Invite already used")

        if invite.expires_at < datetime.now(timezone.utc):
            raise ValueError("Invite has expired")

        return invite

    @staticmethod
    async def use_invite(
        session: AsyncSession,
        invite: TeacherInvite,
        student: Student,
    ) -> Student:
        if student.teacher_id is not None:
            raise ValueError("Student already has a teacher")

        student.teacher_id = invite.teacher_id

        await TeacherInviteRepository.mark_used(
            session,
            invite,
        )

        await session.commit()
        await session.refresh(student)

        return student