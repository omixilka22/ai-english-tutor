from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.database.models import Student, WeeklySchedule
from app.services.recurrence import aware_utc

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
        scheduled_at = aware_utc(scheduled_at)
        student = await session.get(Student, student_id)
        if student is None or student.teacher_id != teacher_id:
            raise ValueError("Учень не належить викладачу.")
        options = {}
        if schedule_id is not None:
            schedule = (await session.execute(select(WeeklySchedule).where(
                WeeklySchedule.id == schedule_id).with_for_update())).scalar_one_or_none()
            if schedule is None or not schedule.active or schedule.teacher_id != teacher_id or schedule.student_id != student_id:
                raise ValueError("Розклад не належить цьому викладачу та учню.")
            local_day = scheduled_at.astimezone(ZoneInfo(schedule.timezone)).date()
            if local_day - timedelta(days=local_day.weekday()) != schedule.week_start:
                raise ValueError('Заняття має належати вибраному календарному тижню.')
            options = dict(occurrence_week=local_day-timedelta(days=local_day.weekday()),
                           duration_minutes=schedule.duration_minutes, timezone=schedule.timezone)
        try:
            return await LessonRepository.create(session, teacher_id, student_id,
                scheduled_at, schedule_id, **options)
        except IntegrityError:
            await session.rollback()
            raise ValueError("Заняття для цього тижня вже існує.") from None

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