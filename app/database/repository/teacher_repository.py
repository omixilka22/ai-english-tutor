from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Teacher


class TeacherRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> Teacher | None:
        result = await session.execute(
            select(Teacher).where(Teacher.id == teacher_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession,
        user_id: int,
    ) -> Teacher | None:
        result = await session.execute(
            select(Teacher).where(Teacher.user_id == user_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
    ) -> Teacher:
        teacher = Teacher(
            user_id=user_id,
        )

        session.add(teacher)
        await session.commit()
        await session.refresh(teacher)

        return teacher

    @staticmethod
    async def get_all(session: AsyncSession) -> list[Teacher]:
        result = await session.execute(
            select(Teacher).order_by(Teacher.id)
        )

        return list(result.scalars().all())