"""Transactional lesson calendar operations shared by bot and background generation."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.database.models import Lesson, LessonStatus, WeeklySchedule, Student, Teacher, User, UserRole
from app.services.notification_service import record_change
from app.services.recurrence import weekly_slots, local_instant, aware_utc


def utcnow():
    return datetime.now(timezone.utc)


def current_week_start(now=None):
    local = aware_utc(now or utcnow()).astimezone(ZoneInfo('Europe/Kyiv'))
    monday = local.date() - timedelta(days=local.weekday())
    return local_instant(monday, datetime.min.time(), 'Europe/Kyiv')


class CalendarService:
    @staticmethod
    async def student_access(session, telegram_id, student_id=None, *, write=False):
        user = (await session.execute(select(User).where(User.telegram_id==telegram_id))).scalar_one_or_none()
        if user is None:
            raise ValueError('Спочатку зареєструйтеся через /start.')
        if user.role == UserRole.STUDENT and not write:
            student = (await session.execute(select(Student).where(Student.user_id==user.id))).scalar_one_or_none()
            if student is not None and (student_id is None or student.id==student_id):
                return student, False
        if user.role == UserRole.TEACHER:
            teacher = (await session.execute(select(Teacher).where(Teacher.user_id==user.id))).scalar_one_or_none()
            student = await session.get(Student,student_id) if student_id is not None else None
            if teacher and student and student.teacher_id==teacher.id:
                return student, True
        raise ValueError('Немає доступу до занять цього учня.')

    @staticmethod
    async def generate_locked(session, schedule, now):
        if not schedule.active:
            return 0
        student = await session.get(Student,schedule.student_id)
        if student is None or student.teacher_id != schedule.teacher_id:
            return 0
        count = 0
        for week, instant in weekly_slots(schedule,now):
            stmt = insert(Lesson).values(teacher_id=schedule.teacher_id,student_id=schedule.student_id,
                schedule_id=schedule.id,occurrence_week=week,scheduled_at=instant,
                duration_minutes=schedule.duration_minutes,timezone=schedule.timezone,
                status=LessonStatus.SCHEDULED,is_exception=False)
            result = await session.execute(stmt.on_conflict_do_nothing(
                constraint='uq_lesson_schedule_week').returning(Lesson.id))
            count += result.scalar_one_or_none() is not None
        return count

    @staticmethod
    async def generate_for_student(session, student_id, now=None):
        now = aware_utc(now or utcnow())
        schedules = (await session.execute(select(WeeklySchedule).where(
            WeeklySchedule.student_id==student_id,WeeklySchedule.active.is_(True)
        ).order_by(WeeklySchedule.id).with_for_update())).scalars().all()
        total = 0
        for schedule in schedules:
            total += await CalendarService.generate_locked(session,schedule,now)
        await session.commit()
        return total

    @staticmethod
    async def upcoming(session, telegram_id, student_id=None):
        student, teacher = await CalendarService.student_access(session,telegram_id,student_id)
        lessons = (await session.execute(select(Lesson).where(Lesson.student_id==student.id,
            Lesson.is_deleted.is_(False),Lesson.scheduled_at>=current_week_start()).order_by(Lesson.scheduled_at,Lesson.id))).scalars().all()
        # A teacher cannot see lessons from a previous teacher.
        if teacher:
            lessons = [l for l in lessons if l.teacher_id==student.teacher_id]
        return student,teacher,lessons

    @staticmethod
    async def history(session, telegram_id, student_id=None):
        student, teacher = await CalendarService.student_access(session, telegram_id, student_id)
        statement = select(Lesson).where(Lesson.student_id == student.id,
            Lesson.is_deleted.is_(False), Lesson.scheduled_at < current_week_start())
        if teacher:
            statement = statement.where(Lesson.teacher_id == student.teacher_id)
        lessons = (await session.execute(statement.order_by(Lesson.scheduled_at.desc(), Lesson.id.desc()).limit(100))).scalars().all()
        return student, teacher, lessons

    @staticmethod
    async def lesson_access(session, telegram_id, lesson_id, *, write=False):
        lesson = await session.get(Lesson,lesson_id)
        if lesson is None or lesson.is_deleted:
            raise ValueError('Заняття не знайдено.')
        if write:
            # Match generation/edit lock order: schedule before lesson.
            if lesson.schedule_id is not None:
                await session.execute(select(WeeklySchedule).where(WeeklySchedule.id==lesson.schedule_id).with_for_update())
            lesson = (await session.execute(select(Lesson).where(Lesson.id==lesson_id)
                .with_for_update().execution_options(populate_existing=True))).scalar_one()
        if lesson.is_deleted:
            raise ValueError('Заняття видалено.')
        student,teacher = await CalendarService.student_access(session,telegram_id,lesson.student_id,write=write)
        if teacher and lesson.teacher_id != student.teacher_id:
            raise ValueError('Заняття належить іншому викладачу.')
        return lesson,teacher

    @staticmethod
    async def create_extra(session, telegram_id, student_id, *, scheduled_at,
                           duration_minutes, timezone_name='Europe/Kyiv'):
        from app.services.schedule_service import ScheduleService
        student,_ = await CalendarService.student_access(session,telegram_id,student_id,write=True)
        scheduled_at = aware_utc(scheduled_at)
        ScheduleService.validate_schedule(scheduled_at.weekday(),scheduled_at.time(),
                                          duration_minutes,timezone_name)
        now = utcnow()
        if scheduled_at <= now:
            raise ValueError('Дата додаткового заняття повинна бути в майбутньому.')
        # Serialize extra-lesson creation for a teacher, including a retry after an uncertain response.
        await session.execute(select(Teacher).where(Teacher.id==student.teacher_id).with_for_update())
        duplicate = (await session.execute(select(Lesson.id).where(
            Lesson.student_id==student.id,Lesson.teacher_id==student.teacher_id,
            Lesson.scheduled_at==scheduled_at,Lesson.status==LessonStatus.SCHEDULED,
            Lesson.is_deleted.is_(False)).limit(1))).scalar_one_or_none()
        if duplicate is not None:
            raise ValueError('Для цього учня вже є заняття на цей час.')
        lesson = Lesson(teacher_id=student.teacher_id,student_id=student.id,
            schedule_id=None,occurrence_week=None,scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,timezone=timezone_name,
            status=LessonStatus.SCHEDULED,is_exception=True,is_deleted=False,
            notification_version=1,notification_since=now)
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
        return lesson

    @staticmethod
    async def change_lesson(session, telegram_id, lesson_id, *, scheduled_at=None, cancel=False):
        lesson,_ = await CalendarService.lesson_access(session,telegram_id,lesson_id,write=True)
        now = utcnow()
        if lesson.status != LessonStatus.SCHEDULED or lesson.scheduled_at<=now:
            raise ValueError('Змінювати можна лише майбутнє заплановане заняття.')
        if cancel:
            lesson.status = LessonStatus.CANCELLED
        else:
            new_time = aware_utc(scheduled_at)
            if new_time<=now:
                raise ValueError('Нова дата повинна бути в майбутньому.')
            if new_time == lesson.scheduled_at:
                return lesson
            lesson.scheduled_at = new_time
        lesson.is_exception = True
        await record_change(session,lesson,'cancelled' if cancel else 'moved',now)
        await session.commit()
        return lesson

    @staticmethod
    async def restore_lesson(session, telegram_id, lesson_id):
        lesson,_ = await CalendarService.lesson_access(session,telegram_id,lesson_id,write=True)
        if lesson.status != LessonStatus.CANCELLED or lesson.scheduled_at <= utcnow():
            raise ValueError('Відновити можна лише скасоване майбутнє заняття.')
        lesson.status = LessonStatus.SCHEDULED
        # Preserve its exact date even if the weekly rule has changed meanwhile.
        lesson.is_exception = True
        await record_change(session,lesson,'restored')
        await session.commit()
        return lesson

    @staticmethod
    async def delete_lesson(session, telegram_id, lesson_id):
        lesson,_ = await CalendarService.lesson_access(session,telegram_id,lesson_id,write=True)
        # Retain the recurrence identity, but hide this lesson from both calendars.
        notify = lesson.status == LessonStatus.SCHEDULED
        lesson.is_deleted = True
        lesson.is_exception = True
        if notify:
            await record_change(session,lesson,'deleted')
        elif lesson.status != LessonStatus.CANCELLED:
            await record_change(session,lesson,None)
        # Keep an unsent cancellation valid; deleting it must not silence that notice.
        await session.commit()
        return lesson

    @staticmethod
    async def update_rule(session, schedule, *, day_of_week, start_time, duration_minutes,
                          timezone, apply_future=False, expected=None):
        raise ValueError('Постійних шаблонів більше немає. Відкрийте конкретне заняття, щоб перенести або скасувати його.')
