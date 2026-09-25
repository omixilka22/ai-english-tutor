from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TeacherInvite


class TeacherInviteRepository:

    @staticmethod
    async def get_by_token(
        session: AsyncSession,
        token: str,
    ) -> TeacherInvite | None:
        result = await session.execute(
            select(TeacherInvite).where(
                TeacherInvite.token == token
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        teacher_id: int,
        token: str,
        expires_at: datetime,
    ) -> TeacherInvite:
        invite = TeacherInvite(
            teacher_id=teacher_id,
            token=token,
            expires_at=expires_at,
        )

        session.add(invite)
        await session.commit()
        await session.refresh(invite)

        return invite

    @staticmethod
    async def mark_used(
        session: AsyncSession,
        invite: TeacherInvite,
    ) -> TeacherInvite:
        invite.used_at = datetime.utcnow()

        await session.commit()
        await session.refresh(invite)

        return invite