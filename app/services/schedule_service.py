from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database.repository.student_repository import StudentRepository

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WeeklySchedule
from app.database.repository.weekly_schedule_repository import (
    WeeklyScheduleRepository,
)


class ScheduleService:

    @staticmethod
    def validate_schedule(day_of_week, start_time, duration_minutes, timezone):
        if not 0 <= day_of_week <= 6:
            raise ValueError("День тижня має бути від 0 до 6.")
        if not 1 <= duration_minutes <= 1440:
            raise ValueError("Тривалість має бути від 1 до 1440 хвилин.")
        if start_time.tzinfo is not None:
            raise ValueError("Вкажіть місцевий час без UTC-зсуву.")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError("Невідомий часовий пояс.") from None

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        schedule_id: int,
    ) -> WeeklySchedule | None:
        return await WeeklyScheduleRepository.get_by_id(
            session,
            schedule_id,
        )

    @staticmethod
    async def get_by_teacher_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> list[WeeklySchedule]:
        return await WeeklyScheduleRepository.get_by_teacher_id(
            session,
            teacher_id,
        )

    @staticmethod
    async def get_by_student_id(
        session: AsyncSession,
        student_id: int,
    ) -> list[WeeklySchedule]:
        return await WeeklyScheduleRepository.get_by_student_id(
            session,
            student_id,
        )

    @staticmethod
    async def create_schedule(
        session: AsyncSession,
        teacher_id: int,
        student_id: int,
        day_of_week: int,
        start_time: time,
        duration_minutes: int,
        timezone: str,
        week_start=None,
    ) -> WeeklySchedule:

        ScheduleService.validate_schedule(
            day_of_week, start_time, duration_minutes, timezone,
        )

        student = await StudentRepository.get_by_id(session, student_id)
        if student is None or student.teacher_id != teacher_id:
            raise ValueError("Учень не належить цьому викладачу.")

        return await WeeklyScheduleRepository.create(
            session,
            teacher_id,
            student_id,
            day_of_week,
            start_time,
            duration_minutes,
            timezone,
            week_start=week_start,
        )

    @staticmethod
    async def update_schedule(
        session: AsyncSession,
        schedule: WeeklySchedule,
        day_of_week: int,
        start_time: time,
        duration_minutes: int,
        timezone: str,
        apply_future: bool = False,
        expected: dict | None = None,
    ) -> WeeklySchedule:

        ScheduleService.validate_schedule(
            day_of_week, start_time, duration_minutes, timezone,
        )

        from app.services.calendar_service import CalendarService
        return await CalendarService.update_rule(
            session, schedule, day_of_week=day_of_week, start_time=start_time,
            duration_minutes=duration_minutes, timezone=timezone,
            apply_future=apply_future, expected=expected,
        )

    @staticmethod
    async def deactivate_schedule(
        session: AsyncSession,
        schedule: WeeklySchedule,
    ) -> WeeklySchedule:
        return await WeeklyScheduleRepository.deactivate(
            session,
            schedule,
        )
