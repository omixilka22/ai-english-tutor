from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WeeklySchedule


class WeeklyScheduleRepository:

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        schedule_id: int,
    ) -> WeeklySchedule | None:
        result = await session.execute(
            select(WeeklySchedule).where(
                WeeklySchedule.id == schedule_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_teacher_id(
        session: AsyncSession,
        teacher_id: int,
    ) -> list[WeeklySchedule]:
        result = await session.execute(
            select(WeeklySchedule).where(
                WeeklySchedule.teacher_id == teacher_id
            )
        )

        return list(result.scalars().all())

    @staticmethod
    async def get_by_student_id(
        session: AsyncSession,
        student_id: int,
    ) -> list[WeeklySchedule]:
        result = await session.execute(
            select(WeeklySchedule).where(
                WeeklySchedule.student_id == student_id
            )
        )

        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        teacher_id: int,
        student_id: int,
        day_of_week: int,
        start_time: time,
        duration_minutes: int,
        timezone: str,
    ) -> WeeklySchedule:
        schedule = WeeklySchedule(
            teacher_id=teacher_id,
            student_id=student_id,
            day_of_week=day_of_week,
            start_time=start_time,
            duration_minutes=duration_minutes,
            timezone=timezone,
        )

        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)

        return schedule

    @staticmethod
    async def update(
        session: AsyncSession,
        schedule: WeeklySchedule,
        day_of_week: int,
        start_time: time,
        duration_minutes: int,
        timezone: str,
    ) -> WeeklySchedule:
        schedule.day_of_week = day_of_week
        schedule.start_time = start_time
        schedule.duration_minutes = duration_minutes
        schedule.timezone = timezone

        await session.commit()
        await session.refresh(schedule)

        return schedule

    @staticmethod
    async def deactivate(
        session: AsyncSession,
        schedule: WeeklySchedule,
    ) -> WeeklySchedule:
        schedule.active = False

        await session.commit()
        await session.refresh(schedule)

        return schedule