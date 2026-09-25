from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Lesson, LessonStatus
from app.database.repository.lesson_repository import LessonRepository


class LessonService:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        lesson_id: int,
    ) -> Lesson | None:
        return await LessonRepository.get_by_id(
            session,
            lesson_id,
        )

    @staticmethod
    async def get_by_teacher_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> list[Lesson]:
        return await LessonRepository.get_by_teacher_id(
            session,
            teacher_id,
        )

    @staticmethod
    async def get_by_student_id(
        session: AsyncSession,
        student_id: int,
    ) -> list[Lesson]:
        return await LessonRepository.get_by_student_id(
            session,
            student_id,
        )

    @staticmethod
    async def create_lesson(
        session: AsyncSession,
        teacher_id: int,
        student_id: int,
        scheduled_at: datetime,
        schedule_id: int | None = None,
    ) -> Lesson:
        return await LessonRepository.create(
            session,
            teacher_id,
            student_id,
            scheduled_at,
            schedule_id,
        )

    @staticmethod
    async def update_status(
        session: AsyncSession,
        lesson: Lesson,
        status: LessonStatus,
    ) -> Lesson:
        return await LessonRepository.update_status(
            session,
            lesson,
            status,
        )