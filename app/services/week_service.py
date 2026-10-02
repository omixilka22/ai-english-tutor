"""Explicit, idempotent publication of a calendar week."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.database.models import Lesson, LessonStatus, WeeklySchedule, WeekRenewal, Teacher, Student
from app.services.calendar_service import utcnow
from app.services.recurrence import week_monday, week_bounds, local_instant


def validate_target(week, now):
    if week not in (week_monday(now), week_monday(now) + timedelta(days=7)):
        raise ValueError('Цей тиждень уже недоступний. Відкрийте розклад знову.')


def renewal_target(now):
    """Sunday 20:00, with catch-up for the current week after a restart."""
    local = now.astimezone(ZoneInfo('Europe/Kyiv'))
    monday = week_monday(now)
    return monday + timedelta(days=7) if local.weekday() == 6 and local.hour >= 20 else monday


def copied_slot(lesson, target, now):
    local = lesson.scheduled_at.astimezone(ZoneInfo('Europe/Kyiv'))
    instant = local_instant(target + timedelta(days=local.weekday()), local.time(), 'Europe/Kyiv', strict=True)
    return None if instant <= now else (local.weekday(), local.time().replace(tzinfo=None), instant)


async def week_lessons(session, teacher_id, week, student_id=None):
    start, end = week_bounds(week)
    query = select(Lesson).join(Student, Student.id == Lesson.student_id).where(
        Lesson.teacher_id == teacher_id, Student.teacher_id == teacher_id,
        Lesson.is_deleted.is_(False), Lesson.scheduled_at >= start, Lesson.scheduled_at < end)
    if student_id is not None:
        query = query.where(Lesson.student_id == student_id)
    return list((await session.execute(query.order_by(Lesson.scheduled_at, Lesson.id))).scalars().all())


async def decision_row(session, teacher_id, week):
    await session.execute(insert(WeekRenewal).values(teacher_id=teacher_id, week_start=week)
        .on_conflict_do_nothing(constraint='uq_teacher_week_renewal'))
    return (await session.execute(select(WeekRenewal).where(
        WeekRenewal.teacher_id == teacher_id, WeekRenewal.week_start == week)
        .with_for_update())).scalar_one()


async def decide(session, teacher_id, week, *, repeat, now=None):
    now = now or utcnow()
    validate_target(week, now)
    # Same lock as manual creation: retries cannot double-publish a week.
    await session.execute(select(Teacher).where(Teacher.id == teacher_id).with_for_update())
    row = await decision_row(session, teacher_id, week)
    if row.decision != 'pending':
        return 0, row.decision
    count = 0
    if repeat:
        source = await week_lessons(session, teacher_id, week - timedelta(days=7))
        existing = await week_lessons(session, teacher_id, week)
        occupied = {(l.student_id, l.scheduled_at) for l in existing}
        for lesson in source:
            if lesson.schedule_id is None or lesson.status == LessonStatus.CANCELLED:
                continue
            slot = copied_slot(lesson, week, now)
            if slot is None:
                continue
            day, clock, instant = slot
            if (lesson.student_id, instant) in occupied:
                continue
            rule = WeeklySchedule(teacher_id=teacher_id, student_id=lesson.student_id,
                week_start=week, day_of_week=day, start_time=clock,
                duration_minutes=lesson.duration_minutes, timezone='Europe/Kyiv', active=True)
            session.add(rule)
            await session.flush()
            session.add(Lesson(teacher_id=teacher_id, student_id=lesson.student_id,
                schedule_id=rule.id, occurrence_week=week, scheduled_at=instant,
                duration_minutes=lesson.duration_minutes, timezone='Europe/Kyiv',
                status=LessonStatus.SCHEDULED, is_deleted=False, is_exception=False,
                notification_version=1, notification_since=now))
            occupied.add((lesson.student_id, instant))
            count += 1
        row.decision = 'repeated'
    else:
        row.decision = 'new'
    await session.commit()
    return count, row.decision
