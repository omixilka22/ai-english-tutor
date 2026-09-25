from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WeeklySchedule
from app.database.repository.weekly_schedule_repository import (
    WeeklyScheduleRepository,
)


class ScheduleService:

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
    ) -> WeeklySchedule:

        if not 0 <= day_of_week <= 6:
            raise ValueError(
                "day_of_week must be between 0 and 6"
            )

        if duration_minutes <= 0:
            raise ValueError(
                "duration_minutes must be greater than 0"
            )

        return await WeeklyScheduleRepository.create(
            session,
            teacher_id,
            student_id,
            day_of_week,
            start_time,
            duration_minutes,
            timezone,
        )

    @staticmethod
    async def update_schedule(
        session: AsyncSession,
        schedule: WeeklySchedule,
        day_of_week: int,
        start_time: time,
        duration_minutes: int,
        timezone: str,
    ) -> WeeklySchedule:

        if not 0 <= day_of_week <= 6:
            raise ValueError(
                "day_of_week must be between 0 and 6"
            )

        if duration_minutes <= 0:
            raise ValueError(
                "duration_minutes must be greater than 0"
            )

        return await WeeklyScheduleRepository.update(
            session,
            schedule,
            day_of_week,
            start_time,
            duration_minutes,
            timezone,
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