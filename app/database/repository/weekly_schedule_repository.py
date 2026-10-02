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
        week_start=None,
    ) -> WeeklySchedule:
        from datetime import timedelta
        from app.database.models import Teacher, Lesson, LessonStatus
        from app.services.recurrence import week_monday, local_instant
        from app.services.calendar_service import utcnow
        now = utcnow()
        week_start = week_start or week_monday(now)
        if week_start not in (week_monday(now), week_monday(now) + timedelta(days=7)):
            raise ValueError('Оберіть поточний або наступний календарний тиждень.')
        instant = local_instant(week_start + timedelta(days=day_of_week), start_time, timezone, strict=True)
        if instant <= now:
            raise ValueError('Цей час уже минув. Оберіть майбутній день і час цього тижня.')
        await session.execute(select(Teacher).where(Teacher.id == teacher_id).with_for_update())
        duplicate = (await session.execute(select(Lesson.id).where(
            Lesson.teacher_id == teacher_id, Lesson.student_id == student_id,
            Lesson.scheduled_at == instant, Lesson.is_deleted.is_(False),
            Lesson.status != LessonStatus.CANCELLED).limit(1))).scalar_one_or_none()
        if duplicate is not None:
            raise ValueError('Для цього учня вже є заняття на цей час.')
        schedule = WeeklySchedule(
            week_start=week_start,
            teacher_id=teacher_id,
            student_id=student_id,
            day_of_week=day_of_week,
            start_time=start_time,
            duration_minutes=duration_minutes,
            timezone=timezone,
        )

        session.add(schedule)
        await session.flush()
        from app.services.calendar_service import CalendarService, utcnow
        await CalendarService.generate_locked(session, schedule, utcnow())
        from app.services.week_service import decision_row
        decision = await decision_row(session, teacher_id, week_start)
        if decision.decision == 'pending':
            decision.decision = 'new'
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