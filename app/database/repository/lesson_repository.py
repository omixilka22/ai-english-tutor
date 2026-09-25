from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Lesson, LessonStatus


class LessonRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> Lesson | None:
        result = await session.execute(
            select(Lesson).where(Lesson.id == lesson_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_teacher_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> list[Lesson]:
        result = await session.execute(
            select(Lesson).where(Lesson.teacher_id == teacher_id)
        )

        return list(result.scalars().all())

    @staticmethod
    async def get_by_student_id(
        session: AsyncSession,
        student_id: int,
    ) -> list[Lesson]:
        result = await session.execute(
            select(Lesson).where(Lesson.student_id == student_id)
        )

        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        teacher_id: int,
        student_id: int,
        scheduled_at: datetime,
        schedule_id: int | None = None,
    ) -> Lesson:
        lesson = Lesson(
            teacher_id=teacher_id,
            student_id=student_id,
            schedule_id=schedule_id,
            scheduled_at=scheduled_at,
        )

        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)

        return lesson

    @staticmethod
    async def update_status(
        session: AsyncSession,
        lesson: Lesson,
        status: LessonStatus,
    ) -> Lesson:
        lesson.status = status

        await session.commit()
        await session.refresh(lesson)

        return lesson