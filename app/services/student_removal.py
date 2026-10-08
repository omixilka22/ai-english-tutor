"""Remove a teacher/student relationship, retaining completed lesson history."""
from datetime import timedelta
from sqlalchemy import select, update
from app.database.models import Student, WeeklySchedule, Lesson, LessonStatus, LessonNotification, LessonAnalysis
from app.services.calendar_service import CalendarService, utcnow


async def remove_student(session, telegram_id, student_id):
    student,_ = await CalendarService.student_access(session,telegram_id,student_id,write=True)
    owner=student.teacher_id
    # Match lesson editing/material delivery: schedules -> lessons -> student.
    schedules=(await session.execute(select(WeeklySchedule).where(
        WeeklySchedule.student_id==student_id,WeeklySchedule.teacher_id==owner)
        .order_by(WeeklySchedule.id).with_for_update())).scalars().all()
    lessons=(await session.execute(select(Lesson).where(
        Lesson.student_id==student_id,Lesson.teacher_id==owner)
        .order_by(Lesson.id).with_for_update())).scalars().all()
    student=(await session.execute(select(Student).where(Student.id==student_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if student is None or student.teacher_id!=owner:
        raise ValueError('Учень уже видалений зі списку або належить іншому викладачу.')
    now=utcnow()
    for schedule in schedules: schedule.active=False
    for lesson in lessons:
        if not lesson.conducted_at and lesson.scheduled_at+timedelta(minutes=lesson.duration_minutes)>now:
            lesson.is_deleted=True
            lesson.status=LessonStatus.CANCELLED
    ids=[lesson.id for lesson in lessons]
    if ids:
        await session.execute(update(LessonNotification).where(
            LessonNotification.lesson_id.in_(ids),LessonNotification.status=='pending')
            .values(status='skipped',last_error='student_removed'))
        await session.execute(update(LessonAnalysis).where(
            LessonAnalysis.lesson_id.in_(ids),LessonAnalysis.workflow_state!='sent')
            .values(workflow_state='blocked',last_error='student_removed',next_attempt_at=None))
    student.teacher_id=None
    student.meeting_url=None
    student.meeting_teacher_id=None
    await session.commit()
