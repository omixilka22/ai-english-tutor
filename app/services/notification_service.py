
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.database.models import Lesson, LessonStatus, LessonNotification, Student, User, UserRole

OFFSETS = {'reminder_12h':timedelta(hours=12), 'reminder_1h':timedelta(hours=1)}
TEACHER_OFFSETS = {'teacher_reminder_1h':timedelta(hours=1), 'teacher_link_15m':timedelta(minutes=15)}
GRACE = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def utcnow():
    return datetime.now(timezone.utc)


def reminder_times(lesson, now, *, teacher=False):
    if lesson.is_deleted or lesson.status != LessonStatus.SCHEDULED or lesson.scheduled_at <= now:
        return []
    result=[]
    for kind,offset in (TEACHER_OFFSETS if teacher else OFFSETS).items():
        due=lesson.scheduled_at-offset
        expires=min(due+GRACE,lesson.scheduled_at)
        if due>=lesson.notification_since and now<=expires:
            result.append((kind,due,expires))
    return result


async def enqueue(session,lesson,kind,due,expires):
    statement=insert(LessonNotification).values(lesson_id=lesson.id,student_id=lesson.student_id,
        revision=lesson.notification_version,kind=kind,due_at=due,expires_at=expires,
        next_attempt_at=due,status='pending',attempts=0)
    await session.execute(statement.on_conflict_do_nothing(constraint='uq_lesson_notification'))


async def record_change(session,lesson,kind,now=None):
    """kind=None invalidates old notifications without creating a change message."""
    now=now or utcnow()
    lesson.notification_version=(getattr(lesson,'notification_version',None) or 1)+1
    lesson.notification_since=now
    if kind is not None and lesson.scheduled_at>now:
        await enqueue(session,lesson,kind,now,min(now+timedelta(hours=24),lesson.scheduled_at))


async def schedule_reminders(session,now=None):
    now=now or utcnow()
    lessons=(await session.execute(select(Lesson).where(
        Lesson.is_deleted.is_(False),Lesson.status==LessonStatus.SCHEDULED,
        Lesson.scheduled_at>now,Lesson.scheduled_at<=now+timedelta(hours=12,minutes=10)
    ))).scalars().all()
    for lesson in lessons:
        for kind,due,expires in reminder_times(lesson,now)+reminder_times(lesson,now,teacher=True):
            await enqueue(session,lesson,kind,due,expires)
    await session.commit()


def invalid_reason(job,lesson,student,user,now,teacher=None):
    if job.kind not in {*OFFSETS, *TEACHER_OFFSETS, 'moved', 'cancelled', 'restored', 'updated', 'deleted'}:
        return 'unknown_kind'
    if now>job.expires_at or lesson is None:
        return 'expired_or_missing'
    if job.revision!=lesson.notification_version or job.student_id!=lesson.student_id:
        return 'lesson_changed'
    expected_role=UserRole.TEACHER if job.kind in TEACHER_OFFSETS else UserRole.STUDENT
    if student is None or user is None or user.role!=expected_role or student.teacher_id!=lesson.teacher_id:
        return 'recipient_unavailable'
    if job.kind in TEACHER_OFFSETS and (teacher is None or teacher.id!=lesson.teacher_id or teacher.user_id!=user.id):
        return 'recipient_unavailable'
    if lesson.scheduled_at<=now:
        return 'lesson_started'
    if job.kind in {*OFFSETS,*TEACHER_OFFSETS}:
        if job.kind in OFFSETS and not student.reminders_enabled:
            return 'disabled'
        if lesson.is_deleted or lesson.status!=LessonStatus.SCHEDULED:
            return 'lesson_inactive'
    elif job.kind=='deleted':
        if not lesson.is_deleted:
            return 'lesson_changed'
    elif job.kind=='cancelled':
        if lesson.status!=LessonStatus.CANCELLED:
            return 'lesson_changed'
    elif lesson.is_deleted:
        return 'lesson_deleted'
    elif job.kind in ('moved','restored','updated') and lesson.status!=LessonStatus.SCHEDULED:
        return 'lesson_changed'
    return None


async def set_preference(session,telegram_id,enabled):
    user=(await session.execute(select(User).where(User.telegram_id==telegram_id))).scalar_one_or_none()
    if user is None or user.role!=UserRole.STUDENT:
        raise ValueError('Це налаштування доступне лише учню.')
    student=(await session.execute(select(Student).where(Student.user_id==user.id).with_for_update())).scalar_one_or_none()
    if student is None:
        raise ValueError('Профіль учня не знайдено.')
    student.reminders_enabled=enabled
    await session.commit()
    return student
